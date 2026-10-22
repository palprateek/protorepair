from __future__ import annotations

from protorepair.extract import extract
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
