"""Engine validation: replay each scenario day by day and plot how the risk score evolves.

Produces docs/engine_validation.png (pitch slide) and prints the final-day table.

    python notebooks/engine_validation.py            # all three demo farms
    python notebooks/engine_validation.py --farm maize

The engine sees, on day t, only the readings up to t - exactly what the API would
have seen if it had been assessing that farm live.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.engine import SCENARIOS, Policy, assess, check_trigger, derive_stage, load_sample_readings  # noqa: E402

TODAY = date(2026, 9, 3)
DEMO_FARMS = {
    "maize": ("maize", 62),  # flowering
    "beans": ("beans", 25),  # vegetative
    "kale": ("kale", 5),  # just planted
}
DROUGHT_POLICY = Policy(type="drought", window_days=21, rainfall_threshold_mm=30)

# Categorical slots from the dataviz reference palette (validated, CVD-safe order).
SERIES = {
    "overall": "#1a1a19",
    "drought": "#eb6834",
    "flood": "#2a78d6",
    "heat": "#eda100",
    "crop_health": "#1baf7a",
}
LABELS = {"overall": "Overall", "drought": "Drought", "flood": "Flood", "heat": "Heat stress", "crop_health": "Crop health"}
OUT = ROOT / "docs" / "engine_validation.png"


def replay(scenario: str, crop: str, days_ago: int) -> dict[str, list[int]]:
    readings = load_sample_readings(scenario, end_date=TODAY)
    planting = TODAY - timedelta(days=days_ago)
    series: dict[str, list[int]] = {k: [] for k in SERIES}
    for i in range(len(readings)):
        upto = readings[: i + 1]
        day = upto[-1].date
        if day < planting:  # crop not in the ground yet -> no score
            for k in series:
                series[k].append(0)
            continue
        st = derive_stage(crop, planting, day)
        a = assess(upto, crop, st)
        series["overall"].append(a.overall.score)
        for k, s in a.sub_scores.items():
            series[k].append(s.score)
    return series


def summary_table(farms: dict[str, tuple[str, int]]) -> None:
    print(f"{'scenario':11s} {'farm':22s} {'drought':>7} {'flood':>5} {'heat':>4} {'health':>6}  overall          trigger(21d<30mm)")
    for sc in SCENARIOS:
        rd = load_sample_readings(sc, end_date=TODAY)
        for crop, dap in farms.values():
            st = derive_stage(crop, TODAY - timedelta(days=dap), TODAY)
            a = assess(rd, crop, st)
            tr = check_trigger(rd, crop, st, DROUGHT_POLICY)
            print(
                f"{sc:11s} {crop + '/' + st.name:22s} {a.drought.score:7d} {a.flood.score:5d} {a.heat.score:4d} "
                f"{a.crop_health.score:6d}  {a.overall.score:3d} {a.overall.level:6s}   "
                f"{'TRIGGERED' if tr.triggered else 'no'} ({tr.evidence['rainfall_total_mm']} mm)"
            )


def plot(farms: dict[str, tuple[str, int]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n_rows, n_cols = len(farms), len(SCENARIOS)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4.6 * n_cols, 3.0 * n_rows), sharex=True, sharey=True, squeeze=False)
    fig.patch.set_facecolor("#fcfcfb")
    x = list(range(-29, 1))

    for r, (farm_key, (crop, dap)) in enumerate(farms.items()):
        for c, sc in enumerate(SCENARIOS):
            ax = axes[r][c]
            ax.set_facecolor("#fcfcfb")
            data = replay(sc, crop, dap)
            for key, color in SERIES.items():
                lw = 2.6 if key == "overall" else 1.6
                ax.plot(x, data[key], color=color, linewidth=lw, solid_capstyle="round", label=LABELS[key])
            # Direct end labels, pushed apart so they never overlap (min 6 score units).
            ends = sorted(((data[k][-1], k) for k in SERIES), key=lambda t: t[0])
            placed: list[float] = []
            for value, key in ends:
                y = value
                if placed and y - placed[-1] < 6:
                    y = placed[-1] + 6
                placed.append(y)
                ax.text(0.6, y, f"{LABELS[key]} {value}", fontsize=7, color="#3b3b38", va="center")
            for y, style in ((30, ":"), (60, ":")):
                ax.axhline(y, color="#c3c2b7", linewidth=0.8, linestyle=style, zorder=0)
            st = derive_stage(crop, TODAY - timedelta(days=dap), TODAY)
            ax.set_title(f"{crop} · {st.name.replace('_', ' ')}  |  {sc.replace('_', ' ')}", fontsize=10, loc="left", color="#1a1a19")
            ax.set_ylim(0, 105)
            ax.set_xlim(-29, 7)
            ax.grid(axis="y", color="#ecebe4", linewidth=0.6)
            for spine in ("top", "right"):
                ax.spines[spine].set_visible(False)
            for spine in ("left", "bottom"):
                ax.spines[spine].set_color("#c3c2b7")
            ax.tick_params(colors="#6f6e66", labelsize=8)
            if c == 0:
                ax.set_ylabel("risk score (0-100)", fontsize=8, color="#6f6e66")
            if r == n_rows - 1:
                ax.set_xlabel("days before today", fontsize=8, color="#6f6e66")

    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, frameon=False, fontsize=8, bbox_to_anchor=(0.5, -0.01))
    fig.suptitle("FarmShield risk engine - score trajectories over the last 30 days (dotted: MEDIUM 30 / HIGH 60)", fontsize=12, x=0.01, ha="left", color="#1a1a19")
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--farm", choices=list(DEMO_FARMS), help="plot a single demo farm")
    ap.add_argument("--no-plot", action="store_true")
    args = ap.parse_args()
    farms = {args.farm: DEMO_FARMS[args.farm]} if args.farm else DEMO_FARMS
    summary_table(farms)
    if not args.no_plot:
        plot(farms)
