from __future__ import annotations

from protorepair.extract import _overlay, extract
from protorepair.fixtures import load_fixture
from protorepair.schema import build_payload_from_recipe, canonical_fields, validate_extraction


def test_schema_payload_valid_for_hero_and_base():
    for fid in ["G02", "G14"]:
        r = load_fixture(fid)
        payload = build_payload_from_recipe(r)
        assert validate_extraction(payload, r.text) == []


def test_field_semantics_maps_by_unit_not_field_name():
    r = load_fixture("G14")
    payload = build_payload_from_recipe(r)
    # Simulate the hero extraction spike's field confusion.
    payload["electrodes"][0]["total_dry_mass"]["value"] = 10.5
    payload["electrodes"][0]["loading"]["value"] = 2.0
    facts = canonical_fields(payload)
    assert facts["total_loading_mg_cm2"] == 10.5
    assert facts["areal_capacity_mAh_cm2"] == 2.0
    assert facts["diameter_mm"] == 14


def test_field_semantics_survives_swapped_gemini_units():
    r = load_fixture("G14")
    payload = build_payload_from_recipe(r)
    payload["electrodes"][0]["loading"] = {
        "value": 10.5, "min": None, "max": None, "unit": "mg/cm2",
        "qualifier": "exact", "raw": "10.5 mg/cm²",
    }
    payload["electrodes"][0]["total_dry_mass"] = {
        "value": 2.0, "min": None, "max": None, "unit": "mAh/cm2",
        "qualifier": "exact", "raw": "2.0 mAh/cm²",
    }
    facts = canonical_fields(payload)
    assert facts["total_loading_mg_cm2"] == 10.5
    assert facts["areal_capacity_mAh_cm2"] == 2.0


def test_overlay_keeps_parser_cam_drying_and_drops_false_a2():
    r = load_fixture("G14")
    payload = build_payload_from_recipe(r)
    payload["electrodes"][0]["drying"] = [{
        "stage": 1,
        "temperature": {"value": 80, "min": None, "max": None, "unit": "C", "qualifier": "exact", "raw": "80 °C"},
        "duration": {"value": 12, "min": None, "max": None, "unit": "h", "qualifier": "at_least", "raw": "at least 12 h"},
        "atmosphere": "vacuum",
        "pressure": {"value": None, "min": None, "max": None, "unit": None, "qualifier": "unknown", "raw": None},
        "endpoint": "before transfer to the glovebox",
        "source_line": 4,
        "quote": "final dry at 80 °C under vacuum for at least 12 h before transfer to the glovebox.",
    }]
    out = _overlay(payload, r.text, r)
    targets = {d.target for d in out.electrode.drying}
    assert {"CAM", "electrode"} <= targets
    assert not any(a.class_id == "A2" for a in out.ambiguities)
    assert out.fixture_id == "G14"


def test_overlay_uses_individual_salt_materials():
    r = load_fixture("G11")
    payload = build_payload_from_recipe(r)
    payload["materials"] = [
        {"name": "LiFSI", "role": "salt", "formula": "LiFSI",
         "amount": {"value": 0.08, "min": None, "max": None, "unit": "M", "qualifier": "exact", "raw": "0.08 M"},
         "source_line": 4, "quote": "0.08 M LiFSI"},
        {"name": "LiDFOB", "role": "salt", "formula": "LiDFOB",
         "amount": {"value": 0.02, "min": None, "max": None, "unit": "M", "qualifier": "exact", "raw": "0.02 M"},
         "source_line": 4, "quote": "0.02 M LiDFOB"},
    ]
    payload["electrolyte"]["concentration"] = {
        "value": 1.0, "min": None, "max": None, "unit": "M", "qualifier": "exact", "raw": "1 M",
    }
    payload["electrolyte"]["quote"] = "0.08 M LiFSI + 0.02 M LiDFOB called 1 M total"
    out = _overlay(payload, r.text, r)
    assert [(s.name, s.concentration_M) for s in out.electrolyte.salts] == [("LiFSI", 0.08), ("LiDFOB", 0.02)]
    assert out.electrolyte.total_molarity == 1.0


def test_no_key_falls_back_without_crashing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = load_fixture("G14")
    outcome = extract(r.text, recipe=r)
    assert outcome.mode == "degraded"
    assert outcome.recipe.electrode.total_loading_mg_cm2 == 10.5
    assert outcome.errors


def test_quote_substring_validation_rejects_bad_quote():
    r = load_fixture("G14")
    payload = build_payload_from_recipe(r)
    payload["electrodes"][0]["drying"] = [{
        "stage": 1,
        "temperature": {"value": 120, "min": None, "max": None, "unit": "C", "qualifier": "exact", "raw": "invented"},
        "duration": {"value": 180, "min": None, "max": None, "unit": "min", "qualifier": "exact", "raw": ""},
        "atmosphere": None,
        "pressure": {"value": 0.001, "min": None, "max": None, "unit": "MPa", "qualifier": "exact", "raw": ""},
        "endpoint": None,
        "source_line": 1,
        "quote": "this text is not on line 1",
    }]
    errors = validate_extraction(payload, r.text)
    assert any("quote" in e for e in errors)
