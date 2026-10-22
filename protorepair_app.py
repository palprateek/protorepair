"""Streamlit entrypoint for ProtoRepair.

The app owns presentation only; checks, patches, evidence, and readiness come
from the package. It works without GEMINI_API_KEY using the structured fixture /
deterministic parse fallback.
"""
from __future__ import annotations

import copy
import hashlib
import os

import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from protorepair.documents import DocumentError, SUPPORTED_EXTENSIONS, extract_document
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
has_gemini_key = bool(os.getenv("GEMINI_API_KEY"))

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
if "document" not in st.session_state:
    st.session_state.document = None
if "document_signature" not in st.session_state:
    st.session_state.document_signature = None

st.sidebar.header("Input")
uploaded = st.sidebar.file_uploader(
    "Upload a protocol document",
    type=sorted(ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS),
    help="PDF, DOCX, TXT, Markdown, LaTeX, or a PNG/JPG/TIFF scan. Tables, figure captions, and OCR text are extracted locally.",
)
if uploaded is not None:
    data = uploaded.getvalue()
    signature = hashlib.sha256(uploaded.name.encode("utf-8") + data).hexdigest()
    if signature != st.session_state.document_signature:
        try:
            with st.spinner(f"Reading {uploaded.name}…"):
                document = extract_document(uploaded.name, data)
            st.session_state.document = document
            st.session_state.document_signature = signature
            st.session_state.fixture_id = None
            st.session_state.protocol_text = document.text
            st.session_state.result = run_pipeline(
                text=document.text,
                source_document=document.summary(),
            )
        except DocumentError as exc:
            st.sidebar.error(str(exc))
        except Exception as exc:
            st.sidebar.error(f"Could not read {uploaded.name}: {exc}")

document = st.session_state.get("document")
if document is not None:
    st.sidebar.success(
        f"Read {document.filename} · {document.kind} · "
        f"{document.pages or '—'} page(s) · {len(document.tables)} table(s) · "
        f"{len(document.figures)} figure(s)"
    )
    if document.warnings:
        with st.sidebar.expander("Reader warnings"):
            for warning in document.warnings:
                st.caption(warning)
    if document.used_ocr:
        st.sidebar.caption("OCR was used; check the extracted text for recognition errors.")

labels = [e[0] for e in examples]
ids = dict(examples)
selected_label = st.sidebar.selectbox("Example protocol", labels, index=labels.index(st.session_state.selected_label))
if selected_label != st.session_state.selected_label:
    fixture_id = ids[selected_label]
    st.session_state.selected_label = selected_label
    st.session_state.fixture_id = fixture_id
    st.session_state.document = None
    result = run_pipeline(fixture_id=fixture_id)
    st.session_state.result = result
    st.session_state.protocol_text = result.recipe.text

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Which path should I use?**\n\n"
    "- **Deterministic checks** are always required. They compute findings, patches, and readiness.\n"
    "- **Use Gemini only when the reader/parser leaves fields missing** from messy prose, tables, or OCR. It fills the parsed fields; it does not decide readiness or write patches.\n"
    "- If the fields are already explicit, skip Gemini; the deterministic parser is enough.\n"
    "- A key is optional. Without one, unknowns stay visible instead of being guessed."
)
with st.sidebar.expander("Why the split?"):
    st.markdown(
        "The AI boundary is **reading**, not checking. Gemini output must pass schema, quote, and unit validation "
        "before the deterministic pipeline sees it. Patches are generated only when a check has a source-faithful target."
    )
if not has_gemini_key:
    st.sidebar.caption("`GEMINI_API_KEY` is not set. The upload/reader and deterministic checks still work.")
st.sidebar.markdown(
    "**Demo modes**\n\n"
    "- Default: committed structured fixtures; checks and patches run live.\n"
    "- Uploaded document: local text/table/OCR extraction; checks run live.\n"
    "- `EVIDENCE_MODE=none` runs the no-Valency ablation."
)
st.sidebar.markdown(attribution())

left, right = st.columns([1.15, 0.85], gap="large")
with left:
    if document is not None:
        st.caption(
            f"Source: uploaded `{document.filename}` · {document.kind} · "
            f"{len(document.tables)} table(s) · {len(document.figures)} figure(s)"
        )
    protocol_text = st.text_area(
        "Protocol text (extracted or pasted)",
        value=st.session_state.protocol_text,
        height=390,
        help="You can edit the extracted text before checking. Table cells and OCR text are included in the text stream.",
    )
    st.session_state.protocol_text = protocol_text
    if document is not None:
        with st.expander("Document reader details"):
            st.write(
                f"Pages: **{document.pages or '—'}** · tables: **{len(document.tables)}** · "
                f"figures/charts: **{len(document.figures)}** · OCR: **{'yes' if document.used_ocr else 'no'}**"
            )
            if document.warnings:
                for warning in document.warnings:
                    st.warning(warning)
            for table in document.tables[:3]:
                st.caption(f"Table {table.number} · {table.method}")
                st.markdown(table.markdown())
            for figure in document.figures[:4]:
                st.caption(f"Figure {figure.number} · {figure.caption or 'no caption'}")
                if figure.ocr_text:
                    st.code(figure.ocr_text[:1500], language="text")
            if document.figures:
                st.caption(
                    "Figures/charts are preserved as captions and OCR labels; plotted data series are not digitized."
                )

    check = st.button("Run deterministic checks", type="primary", use_container_width=True)
    extract_live = st.button(
        "Read with Gemini + run checks (optional)",
        use_container_width=True,
        disabled=not has_gemini_key,
        help="Gemini fills structured fields from messy text. It never decides findings, patches, or readiness.",
    )
    st.caption(
        "Use Gemini when the deterministic parser leaves fields missing. "
        "The checks and patches are deterministic on both paths."
    )

    def _fixture_base(text: str):
        fixture_id = st.session_state.get("fixture_id")
        if not fixture_id:
            return None
        try:
            fixture = load_fixture(fixture_id)
        except KeyError:
            return None
        return fixture if text.strip() == fixture.text.strip() else None

    source_document = document.summary() if document is not None else None

    if extract_live:
        base = _fixture_base(protocol_text)
        outcome = extract(protocol_text, recipe=base)
        if outcome.mode.startswith("gemini"):
            st.session_state.result = run_pipeline(
                recipe=outcome.recipe,
                extraction_mode=outcome.mode,
                source_document=source_document,
            )
            st.success(
                f"Gemini read the source ({outcome.mode}, {outcome.latency_s:.1f} s). "
                "Deterministic checks and patches ran on the extracted fields."
            )
        else:
            st.warning(
                "Gemini extraction unavailable or invalid; continuing with the deterministic/structured fallback. "
                + "; ".join(outcome.errors[:2])
            )
            if base is not None:
                st.session_state.result = run_pipeline(fixture_id=st.session_state.fixture_id)
            else:
                st.session_state.result = run_pipeline(text=protocol_text, source_document=source_document)

if check:
    base = _fixture_base(protocol_text)
    if base is not None:
        result = run_pipeline(fixture_id=st.session_state.fixture_id)
    else:
        result = run_pipeline(text=protocol_text, source_document=source_document)
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

missing = list(result.recipe.missing_fields)
unknown_count = sum(1 for f in result.findings if f.status == "unknown")
if result.extraction_mode.startswith("gemini"):
    st.info(
        "Gemini was used for **reading only**. The findings, patches, and readiness above were produced by the "
        "deterministic checker. Missing values are still shown as unknown, not filled."
    )
elif missing or unknown_count:
    if has_gemini_key:
        st.info(
            f"The deterministic path left **{len(missing)} missing field(s)** and **{unknown_count} unknown finding(s)**. "
            "If the source prose or tables are messy, use **Read with Gemini + run checks**. "
            "Gemini fills extracted fields only; the checks still decide findings and patches."
        )
    else:
        st.warning(
            f"The deterministic path left **{len(missing)} missing field(s)** and **{unknown_count} unknown finding(s)**. "
            "Set `GEMINI_API_KEY` to enable optional reading with Gemini. Unknowns are intentionally not guessed."
        )
else:
    st.success(
        "The deterministic parser found enough explicit fields for the checks. Gemini is not needed for this input."
    )

st.caption(
    "Checks do not fill missing values. They validate stated values and generate a patch only when a check has a "
    "source-faithful target. Gemini may read the source, but it never writes a patch or overrides arithmetic."
)
if result.source_document:
    d = result.source_document
    st.caption(
        f"Document input: {d.get('filename')} · {d.get('pages', 0)} page(s) · "
        f"{d.get('tables', 0)} table(s) · {d.get('figures', 0)} figure(s) · "
        f"OCR {'yes' if d.get('ocr') else 'no'}"
    )

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
        st.session_state.result = run_pipeline(
            recipe=overridden,
            extraction_mode="structured+overrides",
            source_document=result.source_document,
        )
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
