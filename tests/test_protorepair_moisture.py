from __future__ import annotations

import pytest

from protorepair.pipeline import run_pipeline


def test_g14_moisture_table_matches_worked_numbers():
    r = run_pipeline(fixture_id="G14")
    c1 = next(c for c in r.ledger if c.check_id == "C1")
    assert c1.status == "pass"
    assert c1.computed["total_ug_h2o"] == pytest.approx(11.45, abs=0.15)
    assert c1.computed["ppm_on_CAM_basis"] == pytest.approx(745, abs=5)
    assert c1.computed["hf_ppm_equivalent_upper_bound"] == pytest.approx(101, abs=2)
    assert c1.computed["reference_430_ppm"]["basis"] == "Gr/NMC622"


def test_g02_missing_water_uses_scenario_but_remains_unknown():
    r = run_pipeline(fixture_id="G02")
    c1 = next(c for c in r.ledger if c.check_id == "C1")
    assert c1.status == "unknown"
    row_statuses = {row["status"] for row in c1.computed["rows"]}
    assert "scenario" in row_statuses
    assert r.readiness == "REVIEW"


def test_g10_over_limit_is_high_and_patchable():
    r = run_pipeline(fixture_id="G10")
    c1 = [f for f in r.findings if f.class_id == "C1"][0]
    assert c1.status == "fail"
    assert c1.severity == "high"
    assert r.patches[0].before == "1,200 ppm"


def test_component_limits_are_not_universal():
    r = run_pipeline(fixture_id="G14")
    c1 = next(c for c in r.ledger if c.check_id == "C1")
    limits = c1.computed["limits"]
    assert limits["carbon"] is None
    assert limits["PVDF"] is None
    assert limits["NMC811"] == 500
