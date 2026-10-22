from __future__ import annotations

import pytest

from protorepair.fixtures import load_fixture
from protorepair.pipeline import run_pipeline, validate_patch
from protorepair.patches import patch_guardrails


def _has_fixture(fid: str) -> bool:
    try:
        load_fixture(fid)
        return True
    except KeyError:
        return False


@pytest.mark.parametrize(
    "fixture_id",
    [
        "G03", "G04", "G05", "G06", "G08", "G10", "G11",
        pytest.param("G01", marks=pytest.mark.skipif(not _has_fixture("G01"), reason="local-only G01 fixture absent")),
        pytest.param("G12", marks=pytest.mark.skipif(not _has_fixture("G12"), reason="local-only G12 fixture absent")),
    ],
)
def test_each_seeded_fault_patch_is_valid(fixture_id):
    r = run_pipeline(fixture_id=fixture_id)
    assert r.patches, f"{fixture_id} should propose a patch"
    for patch in r.patches:
        assert patch.before in r.recipe.text
        assert patch_guardrails(patch) == []
        result = validate_patch(r, patch)
        assert result["applied"]
        assert result["target_removed"]
        assert result["regressions"] == []


def test_demo_composite_patch_does_not_treat_other_seeded_faults_as_new():
    r = run_pipeline(fixture_id="DEMO")
    assert r.readiness == "NOT READY"
    assert {f.class_id for f in r.findings if f.status == "fail"} == {"B1", "B4", "C2"}
    for patch in r.patches:
        result = validate_patch(r, patch)
        assert result["target_removed"]
        assert result["regressions"] == []


def test_public_transfer_cases():
    assert any(f.class_id == "B3" and f.status == "fail" for f in run_pipeline(fixture_id="G08").findings)
    assert any(f.class_id == "C1" and f.status == "fail" for f in run_pipeline(fixture_id="G10").findings)
    assert any(f.class_id == "B5" and f.status == "fail" for f in run_pipeline(fixture_id="G11").findings)


@pytest.mark.skipif(not (_has_fixture("G01") and _has_fixture("G12")), reason="local-only transfer fixtures absent")
def test_local_transfer_cases():
    assert run_pipeline(fixture_id="G01").readiness == "NOT READY"
    assert any(f.class_id == "C2" and f.status == "fail" for f in run_pipeline(fixture_id="G01").findings)
    assert any(f.class_id == "C2" and f.status == "fail" for f in run_pipeline(fixture_id="G12").findings)


def test_p4_natural_typos_are_ambiguous_not_patched():
    r = run_pipeline(fixture_id="G07")
    assert r.readiness == "REVIEW"
    ambiguous = [f for f in r.findings if f.class_id in {"A1", "A2"}]
    assert {f.class_id for f in ambiguous} == {"A1", "A2"}
    assert all(f.status == "unknown" for f in ambiguous)
    assert not any(f.status == "fail" for f in r.findings)


def test_p5_base_reports_b4_and_c1_unknowns_not_fails():
    r = run_pipeline(fixture_id="G09")
    assert r.readiness == "REVIEW"
    classes = {(f.class_id, f.status) for f in r.findings}
    assert ("B4", "unknown") in classes
    assert ("C1", "unknown") in classes
    assert not any(f.status == "fail" for f in r.findings)


def test_every_finding_has_evidence_or_is_heuristic():
    for fid in ["G02", "G03", "G04", "G05", "G06", "G07", "G08", "G09", "G10", "G11", "G14", "G01", "G12", "G13"]:
        if not _has_fixture(fid):
            continue
        r = run_pipeline(fixture_id=fid)
        for finding in r.findings:
            assert finding.evidence_ids or finding.detection == "heuristic"
