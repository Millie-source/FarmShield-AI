from datetime import date, timedelta

import pytest

from app.engine.crops import get_crop
from app.engine.stages import derive_stage

TODAY = date(2026, 9, 3)


def planted(days_ago: int) -> date:
    return TODAY - timedelta(days=days_ago)


def test_maize_62_days_is_flowering():
    st = derive_stage("maize", planted(62), TODAY)
    assert st.crop == "maize"
    assert st.name == "flowering"
    assert st.day_after_planting == 62
    assert st.day_in_stage == 12  # flowering starts at day 50
    assert st.stage_length_days == 25
    assert st.sensitivity == 1.0
    assert st.is_critical
    assert st.water_need_mm_week == pytest.approx(37.8)  # Kc 1.2 * 4.5 * 7
    assert 0.4 < st.progress < 0.6


def test_kale_5_days_is_establishment():
    st = derive_stage("kale", planted(5), TODAY)
    assert st.name == "establishment"
    assert st.day_in_stage == 5
    assert not st.is_critical


def test_beans_25_days_is_vegetative():
    st = derive_stage("beans", planted(25), TODAY)
    assert st.name == "vegetative"
    assert st.index == 1


def test_stage_boundary_is_inclusive_of_new_stage():
    # maize establishment is 20 days: day 19 is still establishment, day 20 is vegetative
    assert derive_stage("maize", planted(19), TODAY).name == "establishment"
    assert derive_stage("maize", planted(20), TODAY).name == "vegetative"


def test_beyond_season_clamps_to_last_stage():
    season = get_crop("maize").season_length_days
    st = derive_stage("maize", planted(season + 40), TODAY)
    assert st.name == "maturity"
    assert st.progress == 1.0


def test_planting_in_future_raises():
    with pytest.raises(ValueError):
        derive_stage("maize", TODAY + timedelta(days=1), TODAY)


def test_unknown_crop_raises():
    with pytest.raises(ValueError):
        derive_stage("cassava", planted(10), TODAY)


def test_crop_aliases_resolve():
    assert derive_stage("Sukuma Wiki", planted(3), TODAY).crop == "kale"
    assert derive_stage("tomato", planted(3), TODAY).crop == "tomatoes"


@pytest.mark.parametrize("crop", ["maize", "beans", "potatoes", "tomatoes", "kale"])
def test_every_day_of_season_maps_to_a_stage(crop):
    spec = get_crop(crop)
    names = [derive_stage(crop, planted(d), TODAY).name for d in range(spec.season_length_days)]
    assert set(names) == {s.name for s in spec.stages}
    # stages appear in calendar order
    order = [s.name for s in spec.stages]
    assert names == sorted(names, key=order.index)
