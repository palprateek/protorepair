"""Deterministic pre-parser fallback used when no extraction is available.

This is intentionally conservative: it extracts only explicit numbers with units
and records ambiguities rather than guessing. The licensed demo fixtures carry a
structured sidecar and do not depend on this parser.
"""
from __future__ import annotations

import re

from .models import (
    Ambiguity,
    Anode,
    Atmosphere,
    Composition,
    DryingStage,
    Electrode,
    Electrolyte,
    Protocol,
    Recipe,
    Salt,
    Separator,
    default_assumptions,
)
from .preparse import preparse
from .tablefacts import parse_table_facts


def _num(pattern: str, text: str, group: int = 1, flags=0) -> float | None:
    m = re.search(pattern, text, flags)
    return float(m.group(group)) if m else None


def normalize_units_text(text: str) -> str:
    """Make common pasted/LaTeX unit spellings parser-friendly."""
    text = text.replace("\u00a0", " ").replace("−", "-").replace("μ", "µ")
    text = re.sub(r"\bcm\s*(?:\^|\*\*)\s*\{?\s*-\s*2\}?", "cm²", text, flags=re.I)
    text = re.sub(r"\bcm\s*(?:\^|\*\*)\s*\{?\s*2\}?", "cm²", text, flags=re.I)
    text = re.sub(r"\bcm\s*2\b", "cm²", text, flags=re.I)
    text = re.sub(r"\b(mg|mAh|mA)\s+cm²(?=\s|$|[,.;])", r"\1/cm²", text, flags=re.I)
    text = re.sub(r"(?<=\d)\s*(mg|mAh)/cm²(?=[A-Za-z])", r" \1/cm² ", text, flags=re.I)
    text = re.sub(r"\b(um|μm|µm)\b", "µm", text)
    text = re.sub(r"\b(uL|μL|µL)\b", "µL", text)
    text = re.sub(r"\bmA\s+h\b", "mAh", text)
    return text


def _step_for(text: str, needle: str, steps) -> str | None:
    for s in steps:
        if needle in s.text:
            return s.step_id
    return None


def _parse_composition(text: str) -> tuple[float | None, float | None, float | None]:
    m = re.search(
        r"(\d+(?:\.\d+)?)\s*wt%\s*NMC811[^\n]*?(\d+(?:\.\d+)?)\s*wt%\s*(?:Super[^\n,]*?|carbon[^\n,]*?|acetylene[^\n,]*?)[, ]+and\s+(\d+(?:\.\d+)?)\s*wt%\s*PVDF",
        text,
        re.IGNORECASE,
    )
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3))
    m = re.search(r"(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3))
    return None, None, None


def parse_text(text: str) -> Recipe:
    raw_text = text
    text = normalize_units_text(text)
    p = preparse(text)
    steps = p.steps
    lines = p.lines
    title = next((l.strip() for l in lines if l.strip()), "Pasted protocol")
    nmc, carbon, binder = _parse_composition(text)
    stated_active = _num(r"(?:cathode|electrode)\s+contains\s+(\d+(?:\.\d+)?)\s*wt%\s*NMC811", text, flags=re.I)
    solids = _num(r"(\d+(?:\.\d+)?)\s*g\s+total\s+solids", text, flags=re.I)
    nmp = _num(r"(\d+(?:\.\d+)?)\s*mL\s+NMP", text, flags=re.I)
    stated_solids = _num(r"(\d+(?:\.\d+)?)\s*wt%\s+solids", text, flags=re.I)
    purchased = bool(re.search(r"purchased|commercial", text, re.I))

    active_loading = _num(r"(\d+(?:\.\d+)?)\s*mg/cm²\s*active", text, flags=re.I)
    total_loading = _num(r"total\s+dry\s+loading\s+of\s+(\d+(?:\.\d+)?)\s*mg/cm²", text, flags=re.I)
    if total_loading is None:
        total_loading = _num(r"(\d+(?:\.\d+)?)\s*mg/cm²", text, flags=re.I)
    areal = _num(r"(\d+(?:\.\d+)?)\s*mAh/cm²", text, flags=re.I)
    qspec = _num(r"(\d+(?:\.\d+)?)\s*mAh/g", text, flags=re.I)
    diameter = _num(r"(\d+(?:\.\d+)?)\s*mm\s+cathodes", text, flags=re.I)
    if diameter is None:
        diameter = _num(r"punch\s+(\d+(?:\.\d+)?)\s*mm", text, flags=re.I)
    li_um = _num(r"(\d+(?:\.\d+)?)\s*µm\s+Li", text, flags=re.I) or _num(r"Li[^\n]{0,40}?(\d+(?:\.\d+)?)\s*µm", text, flags=re.I)
    vol = _num(r"(\d+(?:\.\d+)?)\s*µL", text, flags=re.I) or _num(r"(\d+(?:\.\d+)?)\s*uL", text, flags=re.I)
    salts = [(m.group(2), float(m.group(1))) for m in re.finditer(r"(\d+(?:\.\d+)?)\s*M\s+(LiPF6|LiFSI|LiDFOB|PQA-NO3)", text)]
    total_M = None
    m_total = re.search(r"(\d+(?:\.\d+)?)\s*M\s+total", text, flags=re.I)
    if m_total:
        total_M = float(m_total.group(1))
    elif len(salts) == 1:
        total_M = salts[0][1]
    sep_m = re.search(r"(\d+(?:\.\d+)?)\s*mm\s+(Whatman\s+GF/A|Celgard\s+\d+|separator)", text, flags=re.I)
    gas_m = re.search(r"\b(Ar|N2|air)\b[^\n]{0,40}?glovebox", text, flags=re.I)
    ppm_m = re.search(r"H2O[^\n]{0,30}?<?\s*(\d+(?:\.\d+)?)\s*ppm", text, flags=re.I)
    o2_m = re.search(r"O2[^\n]{0,30}?<?\s*(\d+(?:\.\d+)?)\s*ppm", text, flags=re.I)

    drying: list[DryingStage] = []
    for s in steps:
        low = s.text.lower()
        if "dry" not in low:
            continue
        temp = _num(r"(\d+(?:\.\d+)?)\s*°C", s.text)
        hours = _num(r"(\d+(?:\.\d+)?)\s*h", s.text)
        vacuum = "vacuum" in low
        target = "CAM" if ("powder" in low or "cam" in low) else "electrode"
        quote = s.text.split("\n")[0]
        drying.append(DryingStage(target, temp, hours, vacuum, quote=quote, step_id=s.step_id))

    water: dict[str, float] = {}
    water_key = {"nmc811": "NMC811", "carbon": "carbon", "pvdf": "PVDF", "separator": "separator", "electrolyte": "electrolyte"}
    for m in re.finditer(r"(NMC811|carbon|PVDF|separator|electrolyte)\s+(?:water\s+(?:content|value)\s+)?(?:is\s+)?(\d[\d,]*)\s*ppm", text, flags=re.I):
        water[water_key[m.group(1).lower()]] = float(m.group(2).replace(",", ""))

    # Conservative table fallback: only fill fields that prose did not state.
    table_comp, table_water, table_values = parse_table_facts(p.tables)
    if nmc is None:
        nmc = table_comp[0]
    if carbon is None:
        carbon = table_comp[1]
    if binder is None:
        binder = table_comp[2]
    for key, value in table_water.items():
        water.setdefault(key, value)
    if total_loading is None:
        total_loading = table_values.get("total_loading")
    if active_loading is None:
        active_loading = table_values.get("active_loading")
    if areal is None:
        areal = table_values.get("areal_capacity")
    if qspec is None:
        qspec = table_values.get("specific_capacity")
    if li_um is None:
        li_um = table_values.get("li_thickness")
    if vol is None:
        vol = table_values.get("electrolyte_volume")
    if diameter is None:
        diameter = table_values.get("cathode_diameter")

    ambiguities: list[Ambiguity] = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*wt%\s*NMP", text, flags=re.I):
        q = m.group(0)
        ambiguities.append(Ambiguity("A1", "composition.nmp_basis", "NMP is given as wt% without a basis.", q,
                                     title="NMP amount has no clear basis",
                                     explanation="The protocol says wt% NMP without saying wt% of what. It is retained as ambiguous, not converted."))
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*mAh\s*(?:g[−-]1|/g)", text, flags=re.I):
        q = m.group(0)
        ambiguities.append(Ambiguity("A2", "electrode.areal_capacity", "A gravimetric capacity unit appears where areal capacity is discussed.", q,
                                     title="Capacity unit/basis ambiguity",
                                     explanation="The value is mAh/g, not mAh/cm². Do not silently convert it."))
    for a in ambiguities:
        a.step_id = _step_for(text, a.quote, steps)

    cell_format = "CR2016" if "CR2016" in text else ("CR2032" if "CR2032" in text else None)
    r = Recipe(
        protocol=Protocol(title=title, cell_format=cell_format),
        text=raw_text,
        steps=steps,
        composition=Composition(
            nmc811_wt=nmc, carbon_wt=carbon, binder_wt=binder, stated_active_wt=stated_active,
            solids_mass_g=solids, nmp_volume_ml=nmp, stated_solids_wt=stated_solids, purchased=purchased,
            composition_quote=(f"{nmc:g} wt% NMC811, {carbon:g} wt% carbon, and {binder:g} wt% PVDF" if nmc else ""),
        ),
        electrode=Electrode(
            total_loading_mg_cm2=total_loading, active_loading_mg_cm2=active_loading,
            areal_capacity_mAh_cm2=areal, specific_capacity_mAh_g=qspec,
            active_fraction=(stated_active / 100.0 if stated_active else (nmc / 100.0 if nmc else None)),
            diameter_mm=diameter, drying=drying,
            quote=next((l.strip() for l in lines if "mAh/cm²" in l or "mg/cm²" in l), ""),
        ),
        anode=Anode(thickness_um=li_um, diameter_mm=None, quote=next((l.strip() for l in lines if "µm Li" in l), "")),
        separator=Separator(material=sep_m.group(2) if sep_m else None, diameter_mm=float(sep_m.group(1)) if sep_m else None),
        electrolyte=Electrolyte(
            volume_uL=vol, volume_basis="total", salts=[Salt(n, c) for n, c in salts], total_molarity=total_M,
            water_ppm=None,
        ),
        atmosphere=Atmosphere(
            gas=gas_m.group(1) if gas_m else None, glovebox=bool(gas_m), h2o_ppm=float(ppm_m.group(1)) if ppm_m else None,
            o2_ppm=float(o2_m.group(1)) if o2_m else None,
        ),
        water_ppm=water,
        assumptions=default_assumptions(),
        ambiguities=ambiguities,
    )
    for a in r.ambiguities:
        a.step_id = r.step_for_quote(a.quote) or a.step_id
    for d in r.electrode.drying:
        d.step_id = d.step_id or r.step_for_quote(d.quote)
    return r
