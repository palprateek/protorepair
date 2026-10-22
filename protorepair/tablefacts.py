"""Conservative table facts used by the deterministic parser.

This is intentionally a small, transparent layer rather than a general table
reasoner.  It recognizes the common composition, water, and parameter/value
layouts found in battery protocols.  The prose parser remains primary; table
values fill only fields that were not stated in prose.
"""
from __future__ import annotations

import re


def _number(cell: str) -> float | None:
    match = re.search(r"(\d+(?:[.,]\d+)?)", str(cell or ""))
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def parse_table_facts(
    tables: list[list[list[str]]],
) -> tuple[tuple[float | None, float | None, float | None], dict[str, float], dict[str, float]]:
    nmc = carbon = binder = None
    water: dict[str, float] = {}
    values: dict[str, float] = {}

    for table in tables:
        if not table:
            continue
        header_index = 0
        for idx, candidate in enumerate(table):
            joined = " ".join(str(cell or "") for cell in candidate).lower()
            if any(token in joined for token in ("material", "component", "parameter", "property", "item", "name")):
                header_index = idx
                break
        header = [re.sub(r"\s+", " ", str(cell or "")).strip().lower() for cell in table[header_index]]
        material_idx = next(
            (i for i, h in enumerate(header) if "material" in h or "component" in h or "name" in h),
            0,
        )
        wt_idx = next(
            (
                i
                for i, h in enumerate(header)
                if "wt" in h or "weight" in h or h in {"%", "percent"}
            ),
            None,
        )
        water_idx = next(
            (i for i, h in enumerate(header) if "water" in h or "h2o" in h or "ppm" in h),
            None,
        )

        for row in table[header_index + 1:]:
            if not row:
                continue
            padded = list(row) + [""] * max(0, len(header) - len(row))
            label = " ".join(padded).lower()
            if material_idx < len(padded):
                label = (padded[material_idx] + " " + label).lower()

            if wt_idx is not None and wt_idx < len(padded):
                value = _number(padded[wt_idx])
                if value is not None:
                    if "nmc811" in label:
                        nmc = value if nmc is None else nmc
                    elif "pvdf" in label:
                        binder = value if binder is None else binder
                    elif any(token in label for token in ("carbon", "c65", "super", "acetylene")):
                        carbon = value if carbon is None else carbon

            if water_idx is not None and water_idx < len(padded):
                value = _number(padded[water_idx])
                if value is not None:
                    for token, key in (
                        ("nmc811", "NMC811"),
                        ("carbon", "carbon"),
                        ("c65", "carbon"),
                        ("pvdf", "PVDF"),
                        ("separator", "separator"),
                        ("electrolyte", "electrolyte"),
                    ):
                        if token in label:
                            water.setdefault(key, value)
                            break

            # Two-column (or wider) parameter/value tables.
            key = padded[0].strip().lower() if padded else ""
            if not key or len(padded) < 2:
                continue
            value_text = " ".join(padded[1:]).strip()
            value = _number(value_text)
            if value is None:
                continue
            if "total dry loading" in key or ("loading" in key and "mg" in value_text):
                values.setdefault("total_loading", value)
            elif "active loading" in key or ("active" in key and "loading" in key):
                values.setdefault("active_loading", value)
            elif "areal capacity" in key:
                values.setdefault("areal_capacity", value)
            elif "specific capacity" in key or "gravimetric capacity" in key:
                values.setdefault("specific_capacity", value)
            elif ("li" in key or "lithium" in key) and ("thickness" in key or "foil" in key):
                values.setdefault("li_thickness", value)
            elif "electrolyte" in key and ("volume" in key or "amount" in key):
                values.setdefault("electrolyte_volume", value)
            elif ("cathode" in key or "electrode" in key) and "diameter" in key:
                values.setdefault("cathode_diameter", value)

    return (nmc, carbon, binder), water, values
