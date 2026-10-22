from __future__ import annotations

import math

import pytest

from protorepair import units
from protorepair.fixtures import load_fixture
from protorepair.pipeline import run_pipeline
from protorepair.report import to_markdown


def test_area_and_p2_arithmetic():
    assert units.area_cm2(14) == pytest.approx(1.539, abs=0.001)
    assert units.area_cm2(12) == pytest.approx(1.131, abs=0.001)
    assert units.q_areal_mAh_cm2(10.5 * 0.95, 200) == pytest.approx(1.995, abs=0.001)


def test_li_and_electrolyte_formulas():
    assert units.li_areal_mAh_cm2(50) == pytest.approx(10.305, abs=0.001)
    assert units.li_ratio(50, 1.995) == pytest.approx(5.165, abs=0.01)
    assert units.electrolyte_uL_per_mAh(200, 2.0, 14) == pytest.approx(64.98, abs=0.1)


def test_solids_balance_uses_one_wt_percent_floor():
    assert units.solids_wt_percent(20, 37.5) == pytest.approx(34.115, abs=0.01)


def test_unit_aliases_and_unknown_unit():
    assert units.convert(1, "mL", "uL") == pytest.approx(1000)
    with pytest.raises(ValueError):
        units.convert(1, "furlong", "mL")


def test_g14_fixture_facts():
    r = load_fixture("G14")
    assert (r.composition.nmc811_wt, r.composition.carbon_wt, r.composition.binder_wt) == (95, 3, 2)
    assert r.electrode.total_loading_mg_cm2 == 10.5
    assert r.electrode.areal_capacity_mAh_cm2 == 2.0
    assert r.electrode.diameter_mm == 14
    assert r.electrolyte.volume_uL == 200
    assert r.anode.thickness_um == 50
    assert r.atmosphere.gas == "Ar"


def test_markdown_export_has_parsed_recipe_original_and_no_merged_protocol():
    md = to_markdown(run_pipeline(fixture_id="G14"))
    assert "## Parsed recipe" in md
    assert "95 : 3 : 2" in md
    assert "## Original input" in md
    assert "## Corrected protocol" not in md
    assert "merged protocol" not in md.lower()
