"""Schema validation and field-semantics reconciliation for LLM extraction.

The model is untrusted: this module rejects invalid JSON/quotes/units and maps
facts by dimension and quote semantics, not by a plausible-sounding field name.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).with_name("schema.json")
SCHEMA_VERSION = "ticket06-frozen-v1"
_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
_DEFS = _SCHEMA.get("$defs", {})


def schema() -> dict:
    return copy.deepcopy(_SCHEMA)


def _resolve(node: dict) -> dict:
    if "$ref" in node:
        name = node["$ref"].split("/")[-1]
        return _resolve(_DEFS[name])
    return node


def instantiate(node: dict) -> Any:
    """Build the smallest schema-valid value; used for tests and cache scaffolding."""
    node = _resolve(node)
    types = node.get("type")
    if isinstance(types, list):
        if "null" in types:
            return None
        types = [t for t in types if t != "null"][0]
    if "enum" in node:
        vals = [v for v in node["enum"] if v is not None]
        return vals[0] if vals else None
    if types == "object" or "properties" in node:
        out = {}
        for key in node.get("required", []):
            out[key] = instantiate(node["properties"][key])
        return out
    if types == "array":
        return []
    if types == "integer":
        return 0
    if types == "number":
        return 0.0
    if types == "boolean":
        return False
    if types == "string":
        return ""
    return None


def validate_extraction(payload: dict, text: str | None = None) -> list[str]:
    errors: list[str] = []
    validator = Draft202012Validator(_SCHEMA)
    for err in sorted(validator.iter_errors(payload), key=lambda e: list(e.path)):
        errors.append(f"schema: {'/'.join(map(str, err.path))}: {err.message}")
    if text is not None:
        lines = text.splitlines()
        def walk(node, path=""):
            if isinstance(node, dict):
                q = node.get("quote")
                line_no = node.get("source_line")
                if isinstance(q, str) and q and isinstance(line_no, int) and 1 <= line_no <= len(lines):
                    if q not in lines[line_no - 1]:
                        errors.append(f"quote: {path}: quote is not a substring of line {line_no}")
                for k, v in node.items():
                    walk(v, f"{path}.{k}" if path else k)
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{path}[{i}]")
        walk(payload)
    return errors


def _measurement(value, unit, raw="", qualifier="exact") -> dict:
    return {"value": value, "min": None, "max": None, "unit": unit, "qualifier": qualifier, "raw": raw}


def build_payload_from_recipe(recipe) -> dict:
    """A schema-valid extraction envelope for cached/demo use.

    This is a deterministic fixture payload, not an LLM response; the UI labels
    the demo path as structured/cached.
    """
    payload = instantiate(_SCHEMA)
    payload["protocol"] = {"title": recipe.protocol.title, "doi": recipe.protocol.doi, "cell_format": recipe.protocol.cell_format}
    payload["atmosphere"] = {
        "assembly_gas": recipe.atmosphere.gas,
        "glovebox": recipe.atmosphere.glovebox,
        "o2_ppm_max": recipe.atmosphere.o2_ppm,
        "h2o_ppm_max": recipe.atmosphere.h2o_ppm,
        "evidence": [],
    }
    payload["materials"] = []
    payload["electrodes"] = []
    if recipe.electrode.total_loading_mg_cm2 is not None:
        item = instantiate(_SCHEMA["properties"]["electrodes"]["items"])
        item["target"] = "cathode"
        item["active_material"] = recipe.electrode.material
        item["composition"] = {
            "active_wt_pct": recipe.composition.nmc811_wt,
            "conductive_wt_pct": recipe.composition.carbon_wt,
            "binder_wt_pct": recipe.composition.binder_wt,
            "raw": recipe.composition.composition_quote or None,
        }
        item["total_dry_mass"] = _measurement(recipe.electrode.total_loading_mg_cm2, "mg/cm2", "total dry loading")
        # Hero spike semantics: mAh/cm2 belongs in loading, regardless of the field name.
        item["loading"] = _measurement(recipe.electrode.areal_capacity_mAh_cm2, "mAh/cm2", "areal capacity")
        item["disc_diameter"] = _measurement(recipe.electrode.diameter_mm, "mm", "disc diameter")
        item["drying"] = [
            {
                "stage": i + 1,
                "temperature": _measurement(d.temp_c, "C", d.quote),
                "duration": _measurement(d.time_h * 60.0 if d.time_h is not None else None, "min", d.quote),
                "atmosphere": None,
                "pressure": _measurement(0.001 if d.vacuum else None, "MPa", d.quote),
                "endpoint": None,
                "source_line": 0,
                "quote": "",
            }
            for i, d in enumerate(recipe.electrode.drying)
        ]
        item["source_lines"] = []
        item["quote"] = ""
        payload["electrodes"].append(item)
    payload["electrolyte"] = {
        "salt": recipe.electrolyte.salts[0].name if recipe.electrolyte.salts else None,
        "concentration": _measurement(recipe.electrolyte.salts[0].concentration_M if recipe.electrolyte.salts else None, "M", "salt concentration"),
        "solvents": [],
        "additives": [],
        "volume": _measurement(recipe.electrolyte.volume_uL, "uL", "electrolyte volume"),
        "volume_basis": recipe.electrolyte.volume_basis,
        "water_ppm_max": recipe.electrolyte.water_ppm,
        "source_line": 0,
        "quote": "",
    }
    payload["separator"] = {
        "material": recipe.separator.material,
        "diameter": _measurement(recipe.separator.diameter_mm, "mm", "separator diameter"),
        "thickness": _measurement(None, None, "not stated", "unknown"),
        "source_line": 0,
        "quote": "",
    }
    payload["steps"] = []
    payload["missing_fields"] = []
    payload["ambiguities"] = []
    return payload


def canonical_fields(payload: dict) -> dict:
    """Map an extraction payload by unit and quote semantics to canonical facts."""
    out: dict[str, Any] = {}
    electrodes = payload.get("electrodes") or []
    if electrodes:
        e = electrodes[0]
        comp = e.get("composition") or {}
        out["composition"] = {
            "nmc811_wt": comp.get("active_wt_pct"),
            "carbon_wt": comp.get("conductive_wt_pct"),
            "binder_wt": comp.get("binder_wt_pct"),
        }
        for _name, m in (("total_dry_mass", e.get("total_dry_mass")), ("loading", e.get("loading")), ("disc_diameter", e.get("disc_diameter"))):
            if not isinstance(m, dict):
                continue
            unit = (m.get("unit") or "").replace("²", "2").lower()
            # Field names are not trustworthy: Gemini has put mg/cm2 in
            # "loading" and mAh/cm2 in "total_dry_mass". The unit decides.
            if unit in {"mg/cm2", "mg/cm^2"}:
                out["total_loading_mg_cm2"] = m.get("value")
            elif unit in {"mah/cm2", "mah/cm^2"}:
                out["areal_capacity_mAh_cm2"] = m.get("value")
            elif unit == "mm":
                out["diameter_mm"] = m.get("value")
            elif unit in {"mah/g", "mah g-1"}:
                out["specific_capacity_mAh_g"] = m.get("value")
        out["drying"] = e.get("drying") or []
    return out
