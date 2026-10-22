"""Markdown and JSON export. Never emit a merged/corrected protocol."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .models import PipelineResult
from .evidence import attribution


DISCLAIMER = (
    "ProtoRepair is a pre-flight consistency checker, not a validated lab protocol or a substitute for "
    "PI/EHS review. It checks arithmetic, stated limits, and text; it cannot validate chemistry, safety, "
    "or whether a cell will work. NMP, Li metal, and HF are hazardous."
)


def _fmt(value, digits=2) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return str(value)


def findings_markdown(result: PipelineResult) -> str:
    if not result.findings:
        return "No findings. No value-changing patches."
    lines = []
    for f in result.findings:
        lines += [
            f"### {f.class_id} · {f.severity.upper()} · {f.status}",
            f"**{f.title}**",
            "",
            f"- Step: `{f.step_id or '—'}` · confidence: {f.confidence} · detection: {f.detection}",
            f"- {f.explanation}",
        ]
        if f.quote:
            lines.append(f"- Quote: “{f.quote}”")
        if f.assumption_ids:
            lines.append(f"- Assumptions: {', '.join(f.assumption_ids)}")
        if f.evidence_ids:
            lines.append(f"- Evidence: {', '.join(f.evidence_ids)}")
        patch = next((p for p in result.patches if p.id == f.patch_id), None)
        if patch:
            lines += ["", "```diff", f"- {patch.before}", f"+ {patch.after}", "```", f"_{patch.rationale}_"]
        elif f.status == "unknown":
            lines += ["", "_No automatic value-changing patch; specify the missing value._"]
        lines.append("")
    return "\n".join(lines)


def moisture_markdown(result: PipelineResult) -> str:
    m = result.moisture or {}
    rows = m.get("rows", [])
    lines = [
        "| Source | Mass (mg/cell) | Water (ppm) | µg H2O | Status | Basis |",
        "|---|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['source']} | {_fmt(row['mass_mg'])} | {_fmt(row['ppm'], 0)} | {_fmt(row['ug_h2o'])} | "
            f"{row['status']} | {row['basis']} |"
        )
    lines += [
        "",
        f"- Total: {_fmt(m.get('total_ug_h2o'))} µg H2O/cell; measured-only total: {_fmt(m.get('measured_total_ug_h2o'))} µg.",
        f"- CAM basis: {_fmt(m.get('ppm_on_CAM_basis'), 0)} ppm.",
        f"- HF upper bound: {_fmt(m.get('hf_upper_ug'))} µg; {_fmt(m.get('hf_ppm_equivalent_upper_bound'), 0)} ppm-eq.",
        "- 430 ppm is a Gr/NMC622 reference warning, not an NMC811 constant.",
        "- Scenario rows are labeled defaults, not measurements.",
    ]
    return "\n".join(lines)


def to_markdown(result: PipelineResult) -> str:
    r = result.recipe
    lines = [
        f"# ProtoRepair report — {r.protocol.title or 'protocol'}",
        "",
        f"**Readiness: {result.readiness}**",
        "",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}._",
        "",
        f"> {DISCLAIMER}",
        "",
        "## Source and license",
        "",
        f"- {r.protocol.source or 'source not stated'}",
        f"- DOI/URL: {r.protocol.url or '—'}",
        f"- License: {r.protocol.license or '—'}",
        f"- Cell format: {r.protocol.cell_format or 'not stated'}",
    ]
    if r.protocol.attribution:
        lines += ["", r.protocol.attribution]
    if result.source_document:
        d = result.source_document
        lines += [
            "",
            "## Document input",
            "",
            f"- File: `{d.get('filename', '—')}` ({d.get('kind', '—')})",
            f"- Pages: {d.get('pages', 0)} · tables: {d.get('tables', 0)} · figures: {d.get('figures', 0)} · OCR: {'yes' if d.get('ocr') else 'no'}",
        ]
        for warning in d.get("warnings") or []:
            lines.append(f"- Reader warning: {warning}")
        for caption in d.get("figure_captions") or []:
            lines.append(f"- Figure caption: {caption}")
    lines += [
        "",
        "## Parsed recipe",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Composition | {_fmt(r.composition.nmc811_wt)} : {_fmt(r.composition.carbon_wt)} : {_fmt(r.composition.binder_wt)} wt% NMC811 : carbon : PVDF |",
        f"| Batch solids / NMP | {_fmt(r.composition.solids_mass_g)} g / {_fmt(r.composition.nmp_volume_ml)} mL |",
        f"| Total dry loading | {_fmt(r.electrode.total_loading_mg_cm2)} mg/cm² |",
        f"| Areal capacity | {_fmt(r.electrode.areal_capacity_mAh_cm2)} mAh/cm² |",
        f"| Specific capacity | {_fmt(r.electrode.specific_capacity_mAh_g)} mAh/g |",
        f"| Electrode diameter | {_fmt(r.electrode.diameter_mm)} mm |",
        f"| Li thickness | {_fmt(r.anode.thickness_um)} µm |",
        f"| Electrolyte fill | {_fmt(r.electrolyte.volume_uL)} µL |",
        f"| Separator | {r.separator.material or '—'}; {_fmt(r.separator.diameter_mm)} mm |",
        f"| Atmosphere | {r.atmosphere.gas or '—'} glovebox={r.atmosphere.glovebox if r.atmosphere.glovebox is not None else '—'}; H2O/O2 {_fmt(r.atmosphere.h2o_ppm)}/{_fmt(r.atmosphere.o2_ppm)} ppm |",
        f"| Water values | {', '.join(f'{k} {v:g} ppm' for k, v in sorted(r.water_ppm.items())) or '—'} |",
        "",
        "## Findings",
        "",
        findings_markdown(result),
        "",
        "## Patches (proposed; never merged)",
        "",
    ]
    if result.patches:
        for p in result.patches:
            lines += [
                f"### {p.id}",
                f"- Finding: `{p.finding_id}` · step `{p.step_id or '—'}` · {p.status}",
                f"- Span: `{p.before}` → `{p.after}`",
                f"- Rationale: {p.rationale}",
                f"- Guardrails: one contiguous span; no step add/delete/reorder; preview only.",
            ]
    else:
        lines.append("No automatic patches.")
    lines += [
        "",
        "## Moisture budget",
        "",
        moisture_markdown(result),
        "",
        "## Missing fields / unknowns",
        "",
        ", ".join(r.missing_fields) if r.missing_fields else "None recorded.",
        "",
        "## Assumptions",
        "",
        "| ID | Default | Use |",
        "|---|---|---|",
    ]
    for a in r.assumptions:
        lines.append(f"| `{a.id}` | {a.default} | {a.use} |")
    lines += [
        "",
        "## Evidence (metadata only)",
        "",
    ]
    for ev in result.evidence.values():
        title = ev.get("title", "")
        url = ev.get("url") or ev.get("doi_or_url")
        lines.append(f"- **{ev.get('id')}** — {title}" + (f" — {url}" if url else "") + f"  \n  {ev.get('claim', '')}")
    if not result.evidence:
        lines.append("EVIDENCE_MODE=none: no external metadata attached; findings remain curated/heuristic.")
    lines += ["", f"_{attribution()}_", "", "## Original input", "", "```text", r.text.strip(), "```", ""]
    return "\n".join(lines)


def to_json(result: PipelineResult) -> str:
    return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)


def diff_text(before: str, after: str) -> str:
    return f"- {before}\n+ {after}"
