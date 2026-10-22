"""Streamlit entrypoint for ProtoRepair.

The app owns presentation only; checks, patches, evidence, and readiness come
from the package. It works without GEMINI_API_KEY using the structured fixture /
deterministic parse fallback.
"""
from __future__ import annotations

import copy
import os

import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from protorepair.evidence import attribution
from protorepair.extract import extract
from protorepair.fixtures import load_fixture, public_examples
from protorepair.models import PipelineResult
from protorepair.patches import apply_patch
from protorepair.pipeline import run_pipeline, validate_patch
from protorepair.report import DISCLAIMER, moisture_markdown, to_json, to_markdown


st.set_page_config(page_title="ProtoRepair", page_icon="🔋", layout="wide")

st.markdown(
    """
    <style>
    .rp-banner {padding: 0.8rem 1rem; border-radius: 0.5rem; margin-bottom: 0.7rem; font-weight: 600;}
    .rp-ready {background:#d9f7e3; color:#0b5d2a; border:1px solid #7bd39a;}
    .rp-review {background:#fff0cc; color:#6b4b00; border:1px solid #e8bf5a;}
    .rp-notready {background:#ffe0df; color:#8b1a1a; border:1px solid #e78b88;}
    .rp-small {color:#555; font-size:0.9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("ProtoRepair")
st.caption("Pre-flight checks for NMC811 || Li-metal coin-cell protocols — findings and local patches, not a rewrite.")

examples = public_examples()
if os.getenv("PROTOREPAIR_LOCAL", "").lower() in {"1", "true", "yes"}:
    for label, fixture_id in [
        ("G01 P1 source (local-only)", "G01"),
        ("G12 P3 dry seed (local-only)", "G12"),
        ("G13 P1 clean control (local-only)", "G13"),
    ]:
        try:
            load_fixture(fixture_id)
            examples.append((label, fixture_id))
        except KeyError:
            # The clean public export deliberately has no .scratch fixtures.
            pass

if "selected_label" not in st.session_state:
    st.session_state.selected_label = examples[0][0]
if "result" not in st.session_state:
    st.session_state.result = run_pipeline(fixture_id="G14")
    st.session_state.fixture_id = "G14"
    st.session_state.protocol_text = st.session_state.result.recipe.text

labels = [e[0] for e in examples]
ids = dict(examples)
selected_label = st.sidebar.selectbox("Example protocol", labels, index=labels.index(st.session_state.selected_label))
if selected_label != st.session_state.selected_label:
    fixture_id = ids[selected_label]
    st.session_state.selected_label = selected_label
    st.session_state.fixture_id = fixture_id
    result = run_pipeline(fixture_id=fixture_id)
    st.session_state.result = result
    st.session_state.protocol_text = result.recipe.text

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Demo modes**\n\n"
    "- Default: committed structured fixtures; checks and patches run live.\n"
    "- Optional Gemini extraction: set `GEMINI_API_KEY` and use the extraction path; it is never required.\n"
    "- `EVIDENCE_MODE=none` runs the no-Valency ablation."
)
st.sidebar.markdown(attribution())

left, right = st.columns([1.15, 0.85], gap="large")
with left:
    protocol_text = st.text_area("Protocol text", value=st.session_state.protocol_text, height=390)
    st.session_state.protocol_text = protocol_text
    check = st.button("Check protocol", type="primary", use_container_width=True)
    extract_live = st.button("Extract with Gemini (live, optional)", use_container_width=True)
    if extract_live:
        fixture_id = st.session_state.get("fixture_id")
        base = load_fixture(fixture_id) if fixture_id and protocol_text.strip() == load_fixture(fixture_id).text.strip() else None
        outcome = extract(protocol_text, recipe=base)
        if outcome.mode.startswith("gemini"):
            st.session_state.result = run_pipeline(recipe=outcome.recipe, extraction_mode=outcome.mode)
            st.success(f"Gemini extraction accepted ({outcome.mode}, {outcome.latency_s:.1f} s).")
        else:
            st.warning("Gemini extraction unavailable or invalid; continuing with the deterministic/structured fallback. " + "; ".join(outcome.errors[:2]))
            if base is not None:
                st.session_state.result = run_pipeline(fixture_id=fixture_id)
            else:
                st.session_state.result = run_pipeline(text=protocol_text)

if check:
    fixture_id = st.session_state.get("fixture_id")
    if fixture_id:
        fixture = load_fixture(fixture_id)
        if protocol_text.strip() == fixture.text.strip():
            result = run_pipeline(fixture_id=fixture_id)
        else:
            result = run_pipeline(text=protocol_text)
    else:
        result = run_pipeline(text=protocol_text)
    st.session_state.result = result

result: PipelineResult = st.session_state.result

with right:
    color = {"READY": "rp-ready", "REVIEW": "rp-review", "NOT READY": "rp-notready"}[result.readiness]
    st.markdown(f'<div class="rp-banner {color}">Readiness: {result.readiness}</div>', unsafe_allow_html=True)
    c = result.counts
    cols = st.columns(4)
    for col, key, label in zip(cols, ["critical", "high", "medium", "low"], ["Critical", "High", "Medium", "Low"]):
        col.metric(label, c.get(key, 0))
    fails = sum(1 for f in result.findings if f.status == "fail")
    unknowns = sum(1 for f in result.findings if f.status == "unknown")
    st.markdown(
        f"**{fails} fail** · **{unknowns} unknown** · "
        f"**{len(result.patches)} proposed patch(es)** · extraction: `{result.extraction_mode}`"
    )
    if result.warnings:
        st.warning("; ".join(result.warnings))
    if result.readiness == "READY":
        st.caption("No Critical/High/Medium finding and no material unknown. Low/advisory notes may remain.")
    elif result.readiness == "REVIEW":
        st.caption("No Critical/High finding; a Medium finding or material unknown blocks READY.")
    else:
        st.caption("At least one Critical/High finding. Critical findings cannot be acknowledged away.")

st.markdown(f"> {DISCLAIMER}")
st.markdown("---")

tabs = st.tabs(["Findings", "Moisture budget", "Assumptions / overrides", "Evidence", "Export"])
with tabs[0]:
    if not result.findings:
        st.success("No findings. No value-changing patches.")
    for f in result.findings:
        with st.container(border=True):
            cols = st.columns([0.72, 0.28])
            with cols[0]:
                st.markdown(f"### {f.class_id} · {f.status.upper()} · {f.severity.upper()}")
                st.markdown(f"**{f.title}**")
                st.markdown(f"`{f.step_id or '—'}` · confidence **{f.confidence}** · detection **{f.detection}**")
                st.write(f.explanation)
                if f.quote:
                    st.caption(f"Quote: “{f.quote}”")
                if f.assumption_ids:
                    st.caption("Assumptions: " + ", ".join(f.assumption_ids))
                if f.evidence_ids:
                    st.caption("Evidence: " + ", ".join(f.evidence_ids))
            with cols[1]:
                st.metric("Severity", f.severity.upper())
                if f.status == "unknown":
                    st.info("Unknown is REVIEW-level; no invented value.")
            patch = next((p for p in result.patches if p.id == f.patch_id), None)
            if patch:
                st.markdown("**Proposed local patch (preview only; never merged)**")
                st.code(f"- {patch.before}\n+ {patch.after}", language="diff")
                st.caption(patch.rationale)
                if st.button("Preview patched text", key=f"preview-{patch.id}"):
                    try:
                        patched_text, _ = apply_patch(result.recipe, patch)
                        st.code(patched_text, language="text")
                        validity = validate_patch(result, patch)
                        if validity["target_removed"] and not validity["regressions"]:
                            st.success("Patch validity: target finding removed on rerun; no new fail.")
                        else:
                            st.warning(f"Patch validity: {validity}")
                    except Exception as exc:  # keep the demo alive
                        st.error(f"Patch could not be applied: {exc}")

with tabs[1]:
    m = result.moisture or {}
    rows = m.get("rows", [])
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
        cols = st.columns(4)
        cols[0].metric("Total µg H2O/cell", f"{m.get('total_ug_h2o', 0):.1f}")
        cols[1].metric("CAM basis ppm", "—" if m.get("ppm_on_CAM_basis") is None else f"{m['ppm_on_CAM_basis']:.0f}")
        cols[2].metric("HF upper bound ppm-eq", "—" if m.get("hf_ppm_equivalent_upper_bound") is None else f"{m['hf_ppm_equivalent_upper_bound']:.0f}")
        cols[3].metric("430 ppm reference", "Gr/NMC622 only")
        st.warning("430 ppm is a Gr/NMC622 reference warning, not an NMC811 constant. Scenario rows are labeled defaults, not measurements.")
        st.markdown(moisture_markdown(result))
    else:
        st.info("No moisture table available.")

with tabs[2]:
    st.caption("Every arithmetic default is shown. Changing a value is recorded in the export; deterministic checks still use the named assumption unless the parsed recipe is overridden below.")
    for a in result.recipe.assumptions:
        st.text(f"{a.id}: {a.default} — {a.use}")
    st.markdown("**Editable parsed recipe (minimum override surface)**")
    e = result.recipe.electrode
    with st.form("recipe-overrides"):
        total = st.number_input("Total dry loading (mg/cm²)", value=float(e.total_loading_mg_cm2 or 0.0), step=0.1)
        areal = st.number_input("Areal capacity (mAh/cm²)", value=float(e.areal_capacity_mAh_cm2 or 0.0), step=0.1)
        qspec = st.number_input("Specific capacity (mAh/g)", value=float(e.specific_capacity_mAh_g or 200.0), step=1.0)
        li = st.number_input("Li thickness (µm; 0 = unknown)", value=float(result.recipe.anode.thickness_um or 0.0), step=1.0)
        vol = st.number_input("Electrolyte volume (µL; 0 = unknown)", value=float(result.recipe.electrolyte.volume_uL or 0.0), step=1.0)
        submitted = st.form_submit_button("Re-run with these parsed values")
    if submitted:
        overridden = copy.deepcopy(result.recipe)
        overridden.electrode.total_loading_mg_cm2 = total or None
        overridden.electrode.areal_capacity_mAh_cm2 = areal or None
        overridden.electrode.specific_capacity_mAh_g = qspec or None
        overridden.anode.thickness_um = li or None
        overridden.electrolyte.volume_uL = vol or None
        st.session_state.result = run_pipeline(recipe=overridden, extraction_mode="structured+overrides")
        st.rerun()

with tabs[3]:
    st.caption(attribution())
    if not result.evidence:
        st.info("No evidence metadata loaded (EVIDENCE_MODE=none or no snapshot). Findings fall back to curated/heuristic text.")
    for ev in result.evidence.values():
        with st.container(border=True):
            st.markdown(f"**{ev.get('id')}** — {ev.get('title', '')}")
            meta = " · ".join(str(x) for x in [ev.get("authors"), ev.get("venue"), ev.get("year")] if x)
            st.caption(meta)
            st.write(ev.get("claim", ""))
            url = ev.get("url") or ev.get("doi_or_url")
            if url:
                st.markdown(f"[DOI/URL]({url})")
            st.caption("Metadata only; no abstract or raw Valency output.")

with tabs[4]:
    st.caption("Export contains the original text, parsed recipe, assumptions, findings, patches, evidence metadata, readiness, and missing fields. It never contains a merged protocol.")
    col1, col2 = st.columns(2)
    col1.download_button("Download JSON", to_json(result), file_name="protorepair-report.json", mime="application/json")
    col2.download_button("Download Markdown", to_markdown(result), file_name="protorepair-report.md", mime="text/markdown")
    with st.expander("JSON preview"):
        st.code(to_json(result)[:12000], language="json")
