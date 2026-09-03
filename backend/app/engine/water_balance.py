"""Daily soil-water balance: models soil moisture where the station has no probe.

The JKUAT Conduit@Empathy station reports rain, temperature, humidity, wind,
Heat Index and WBGT, but *no soil moisture and no W/m2 solar radiation*.  Drought
and flood scoring still need a soil-water state, so this module computes one:

1. **Reference ET0** per day with the Hargreaves-Samani equation (FAO-56 eq. 52),
   which needs only Tmin / Tmax / Tmean, latitude and day-of-year - exactly what
   the station gives.  Extraterrestrial radiation Ra follows FAO-56 eq. 21-25.
   An optional 0-1 light index (SI1145 visible/IR, relative to the file maximum)
   may scale ET0 by at most +/-10 % (overcast vs. clear days).
2. **Crop ET**: ETc = ET0 x Kc(stage) (FAO-56 ch. 6), with bare-soil Kc before
   planting and a stress coefficient Ks that throttles transpiration as the
   bucket approaches the wilting point (FAO-56 ch. 8).
3. **Soil bucket** (single layer, FAO-56 ch. 8 root-zone depletion) expressed as
   volumetric water content %: rain infiltrates up to saturation (excess = runoff),
   water above field capacity drains at DRAIN_FRACTION per day, ETc withdraws.

Default soil: Juja red clay-loam (humic nitisol).  Every consumer must label the
output "modelled soil moisture" - it is an estimate, not a measurement.  When a
reading *does* carry a measured ``soil_moisture_pct`` the bucket is reset to it
(simple data assimilation), so a future probe slots in without code changes.

Stdlib only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .crops import CropSpec
from .types import Reading

JUJA_LAT = -1.0997  # JKUAT Conduit@Empathy station
HARGREAVES_COEFF = 0.0023
MJ_TO_MM = 0.408  # 1 MJ m-2 day-1 of latent heat ~ 0.408 mm evaporation (FAO-56 eq. 20)
LIGHT_ET_RANGE = 0.10  # light index may move ET0 by at most +/-10 %
BARE_SOIL_KC = 0.30  # before planting / fallow (FAO-56 Kc_ini lower bound)
DRAIN_FRACTION = 0.40  # share of water above field capacity that drains each day
KS_DEPLETION_START = 0.5  # Ks starts falling once half the readily available water is used


@dataclass(frozen=True)
class SoilType:
    name: str
    wilting_point_pct: float  # permanent wilting point, vol. %
    field_capacity_pct: float  # vol. %
    saturation_pct: float  # vol. %
    root_depth_mm: float  # effective root-zone depth used for the bucket

    @property
    def mm_per_pct(self) -> float:
        return self.root_depth_mm / 100.0


# Nitisol values: Batjes (2008) / KALRO soil survey for Kiambu red clay loams.
SOIL_TYPES: dict[str, SoilType] = {
    "juja_red_clay_loam": SoilType("Juja red clay-loam (nitisol)", 18.0, 38.0, 46.0, 600.0),
    "sandy_loam": SoilType("Sandy loam", 10.0, 24.0, 40.0, 600.0),
    "black_cotton_clay": SoilType("Black cotton clay (vertisol)", 22.0, 44.0, 52.0, 600.0),
}
DEFAULT_SOIL = SOIL_TYPES["juja_red_clay_loam"]


@dataclass(frozen=True)
class DayBalance:
    date: date
    et0_mm: float
    kc: float
    etc_mm: float  # actual crop ET after stress coefficient
    rain_mm: float
    runoff_mm: float
    drainage_mm: float
    soil_moisture_pct: float
    measured: bool  # True when the bucket was reset to a probe value


# --------------------------------------------------------------------- ET0 ----
def extraterrestrial_radiation_mj(lat_deg: float, doy: int) -> float:
    """Daily extraterrestrial radiation Ra [MJ m-2 day-1], FAO-56 eq. 21-25."""
    lat = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)  # inverse relative distance
    decl = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)  # solar declination
    ws = math.acos(max(-1.0, min(1.0, -math.tan(lat) * math.tan(decl))))  # sunset hour angle
    gsc = 0.0820  # solar constant MJ m-2 min-1
    return (24 * 60 / math.pi) * gsc * dr * (ws * math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.sin(ws))


def et0_hargreaves(tmin_c: float, tmax_c: float, tmean_c: float | None, lat_deg: float, doy: int, light_index: float | None = None) -> float:
    """Reference evapotranspiration [mm/day] via Hargreaves-Samani (FAO-56 eq. 52)."""
    tmean = tmean_c if tmean_c is not None else (tmax_c + tmin_c) / 2
    trange = max(0.0, tmax_c - tmin_c)
    ra_mm = extraterrestrial_radiation_mj(lat_deg, doy) * MJ_TO_MM
    et0 = HARGREAVES_COEFF * ra_mm * (tmean + 17.8) * math.sqrt(trange)
    if light_index is not None:
        # 0 -> overcast (-10 %), 0.5 -> neutral, 1 -> clear sky (+10 %)
        et0 *= 1 + LIGHT_ET_RANGE * (2 * max(0.0, min(1.0, light_index)) - 1)
    return max(0.0, round(et0, 2))


# ---------------------------------------------------------------------- Kc ----
def kc_on_day(spec: CropSpec, day_after_planting: int) -> float:
    """Kc for a given day after planting (bare soil before planting, last stage Kc after season end)."""
    if day_after_planting < 0:
        return BARE_SOIL_KC
    cursor = 0
    for st in spec.stages:
        cursor += st.days
        if day_after_planting < cursor:
            return st.kc
    return spec.stages[-1].kc


def _ks(vwc: float, soil: SoilType) -> float:
    """Water-stress coefficient: 1 when wet, linear to 0 at the wilting point (FAO-56 eq. 84 simplified)."""
    taw = soil.field_capacity_pct - soil.wilting_point_pct
    threshold = soil.wilting_point_pct + KS_DEPLETION_START * taw
    if vwc >= threshold:
        return 1.0
    return max(0.0, (vwc - soil.wilting_point_pct) / (threshold - soil.wilting_point_pct))


# ------------------------------------------------------------------ bucket ----
def simulate(
    readings: Iterable[Reading],
    spec: CropSpec,
    planting_date: date,
    soil: SoilType = DEFAULT_SOIL,
    lat_deg: float = JUJA_LAT,
    initial_pct: float | None = None,
) -> list[DayBalance]:
    """Run the daily bucket over ``readings`` (any order; sorted here). Returns one DayBalance per reading.

    ``initial_pct`` defaults to field capacity: the demo season starts after the long rains, and a
    30-day history is enough for the bucket to forget that assumption under dry conditions.
    """
    ordered = sorted(readings, key=lambda r: r.date)
    vwc = soil.field_capacity_pct if initial_pct is None else initial_pct
    out: list[DayBalance] = []
    for r in ordered:
        measured = r.soil_moisture_pct is not None
        dap = (r.date - planting_date).days
        kc = kc_on_day(spec, dap)
        et0 = et0_hargreaves(r.temp_min_c, r.temp_max_c, r.temp_mean_c, lat_deg, r.date.timetuple().tm_yday, r.light_index)
        etc = et0 * kc * _ks(vwc, soil)
        if measured:
            # A probe reading is the truth for that day: report it as-is and restart the bucket from it.
            vwc = round(float(r.soil_moisture_pct), 1)  # type: ignore[arg-type]
            out.append(DayBalance(r.date, et0, kc, round(etc, 2), r.rainfall_mm, 0.0, 0.0, vwc, True))
            continue

        storage = vwc * soil.mm_per_pct
        capacity = soil.saturation_pct * soil.mm_per_pct
        infiltration = min(r.rainfall_mm, max(0.0, capacity - storage))
        runoff = r.rainfall_mm - infiltration
        storage += infiltration
        fc_mm = soil.field_capacity_pct * soil.mm_per_pct
        drainage = max(0.0, storage - fc_mm) * DRAIN_FRACTION
        storage -= drainage
        storage = max(soil.wilting_point_pct * soil.mm_per_pct, storage - etc)
        vwc = round(storage / soil.mm_per_pct, 1)
        out.append(DayBalance(r.date, et0, kc, round(etc, 2), r.rainfall_mm, round(runoff, 1), round(drainage, 1), vwc, measured))
    return out


def soil_moisture_series(readings: Iterable[Reading], spec: CropSpec, planting_date: date, soil: SoilType = DEFAULT_SOIL) -> dict[date, DayBalance]:
    return {b.date: b for b in simulate(readings, spec, planting_date, soil)}
