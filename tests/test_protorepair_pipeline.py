from __future__ import annotations

import pytest

from protorepair.fixtures import load_fixture
from protorepair.pipeline import run_pipeline


def _has_fixture(fid: str) -> bool:
    try:
        load_fixture(fid)
        return True
    except KeyError:
        return False


def test_g14_clean_control_is_ready_with_no_findings():
    r = run_pipeline(fixture_id="G14")
    assert r.readiness == "READY"
    assert r.findings == []
    assert r.patches == []


@pytest.mark.skipif(not _has_fixture("G13"), reason="local-only G13 fixture not present in public export")
def test_g13_clean_control_is_ready():
    r = run_pipeline(fixture_id="G13")
    assert r.readiness == "READY"
    assert r.findings == []


def test_g02_base_is_review_with_expected_unknowns():
    r = run_pipeline(fixture_id="G02")
    assert r.readiness == "REVIEW"
    classes = {(f.class_id, f.status) for f in r.findings}
    assert ("B1", "unknown") in classes
    assert ("B3", "unknown") in classes
    assert ("C1", "unknown") in classes
    assert ("C2", "unknown") in classes
    assert not any(f.status == "fail" for f in r.findings)
    assert r.patches == []


@pytest.mark.parametrize("fixture_id", ["G02", "G03", "G04", "G05", "G06", "G07", "G08", "G09", "G10", "G11"])
def test_every_finding_is_tied_to_a_step(fixture_id):
    r = run_pipeline(fixture_id=fixture_id)
    assert all(f.step_id for f in r.findings)


def test_pasted_text_uses_deterministic_fallback_label():
    text = "1. Mix 95 wt% NMC811, 3 wt% carbon, and 2 wt% PVDF in NMP.\n2. Coat at 10.5 mg/cm2; dry at 80 C."
    r = run_pipeline(text=text)
    assert r.extraction_mode == "deterministic"
    assert r.readiness in {"REVIEW", "NOT READY"}
    assert r.recipe.text == text


def test_h1_composition_fail_and_patch():
    r = run_pipeline(fixture_id="G03")
    fails = [f for f in r.findings if f.status == "fail"]
    assert r.readiness == "NOT READY"
    assert [(f.class_id, f.severity) for f in fails] == [("B1", "high")]
    patch = r.patches[0]
    assert patch.before == "90 wt% NMC811, 5 wt% Super C65 carbon black, and 5 wt% PVDF"
    assert patch.after == "95 wt% NMC811, 3 wt% Super C65 carbon black, and 2 wt% PVDF"


def test_h2_capacity_fail_and_patch():
    r = run_pipeline(fixture_id="G04")
    fails = [f for f in r.findings if f.status == "fail"]
    assert r.readiness == "NOT READY"
    assert [(f.class_id, f.severity) for f in fails] == [("B2", "high")]
    assert r.patches[0].before == "21 mg/cm²"
    assert r.patches[0].after == "10.5 mg/cm²"
    assert r.patches[0].field_updates["electrode.total_loading_mg_cm2"] == 10.5


def test_h3_underfill_is_review_isolated():
    r = run_pipeline(fixture_id="G05")
    fails = [f for f in r.findings if f.status == "fail"]
    assert r.readiness == "REVIEW"
    assert [(f.class_id, f.severity) for f in fails] == [("B4", "medium")]
    assert r.patches[0].after == "200 µL"


def test_h4_n2_is_critical():
    r = run_pipeline(fixture_id="G06")
    fails = [f for f in r.findings if f.status == "fail"]
    assert r.readiness == "NOT READY"
    assert [(f.class_id, f.severity) for f in fails] == [("C2", "critical")]
    assert r.patches[0].before == "an N2 glovebox"
    assert r.patches[0].after == "an Ar glovebox"
