# ProtoRepair

![ProtoRepair cover](docs/assets/protorepair-cover.png)

**Pre-flight consistency checks for NMC811 || Li-metal coin-cell protocols.**

[Watch the 3:12 tutorial](docs/assets/protorepair-tutorial.mp4) · [Gallery card](docs/assets/protorepair-gallery-card.png) · [Write-up](writeup.md)

Paste an assembly excerpt or upload a protocol document. ProtoRepair returns **findings + one local patch per finding**, backed by explicit arithmetic, units, and metadata-only evidence. It does **not** rewrite the protocol, merge a corrected version, or emit a numeric “protocol score.”

## Read a real protocol

The app reads documents locally before any model is involved:

- **PDF** — text, layout, and tables via `pdfplumber`; scanned pages render through Poppler and OCR through Tesseract.
- **DOCX** — paragraphs, tables, embedded images, and Office math text via `python-docx`.
- **LaTeX** — `.tex`/`.latex`, including `siunitx` (`\SI{21}{mg/cm^2}`), simple `tabular` tables, and common math/unit spellings via `pylatexenc`.
- **TXT / Markdown** — text and Markdown tables; **PNG / JPG / TIFF** — OCR of a single scanned page.
- **Tables** are preserved as Markdown and common composition/water/parameter tables also feed the deterministic parser.
- **Figures and charts** are retained as captions plus OCR labels. Plotted numerical series are **not** digitized; OCR text is evidence, not a data table.
- **Scanned tables** are best-effort: OCR can preserve rows, but borderless or low-resolution scans may lose column structure.

The reader is offline. OCR and PDF rendering need system tools:

```bash
# Debian/Ubuntu example
sudo apt-get install poppler-utils tesseract-ocr
```

If OCR is unavailable, text PDFs and DOCX still work; the app shows a reader warning instead of failing.

## Which path should I use?

| Input state | What to do |
|---|---|
| Clean numbered protocol with explicit units | Use **Run deterministic checks**. Gemini is not needed. |
| Messy prose, table-heavy document, or noisy OCR | Optionally use **Read with Gemini + run checks**. Gemini only fills the parsed fields. |
| Missing value (for example, no Li thickness) | Leave it unknown. Gemini cannot invent a value; the checker reports the unknown. |
| Findings, patches, readiness | Always deterministic. Gemini never writes a patch or overrides arithmetic. |

The sidebar and the post-run guidance card state the same rule: **AI reads; code checks.** The Gemini button is disabled when `GEMINI_API_KEY` is absent. Without a key, the reader, deterministic parser, checks, patches, and exports still work.

Readiness is one of **`NOT READY`**, **`REVIEW`**, or **`READY`**:

- **NOT READY**: at least one Critical/High finding.
- **REVIEW**: no Critical/High finding, but a Medium finding or material unknown remains.
- **READY**: no remaining Medium-or-worse fail or material unknown. Low/advisory notes may remain.

> ProtoRepair is not a validated lab protocol and not a substitute for PI/EHS review. It checks text, arithmetic, and stated limits; it cannot validate chemistry, safety, or whether a cell will work. NMP, Li metal, and HF are hazardous.

## What it checks

| Group | Check | What it catches |
|---|---|---|
| A | A1 / A3 | missing or ambiguous units/bases; unowned magnitude errors |
| B1 | composition / solids | fractions that do not sum to 100 wt%; composition prose that disagrees with the line; batch solids vs NMP |
| B2 | loading ↔ capacity | active loading × specific capacity vs stated areal capacity |
| B3 | Li excess | Li foil areal capacity vs cathode capacity; anode-limited cells; claimed ratio mismatch |
| B4 | electrolyte fill | µL/mAh and g/Ah; under-wetting screen |
| B5 | salt molarity | mixed-salt concentrations vs stated total molarity |
| C1 | moisture budget | per-cell water mass, CAM-basis ppm, HF upper bound, component limits |
| C2 | atmosphere / drying | N₂ or air for Li metal; incomplete or low-temperature CAM/electrode drying |
| D1/D4 | semantic/advisory | undefined references and assembly-only omissions |

The checks are deterministic. Gemini extraction is optional and untrusted: output must pass JSON Schema, line/quote, and unit/basis reconciliation before it reaches the checks. With no key, the app uses structured fixtures or the deterministic parser and says so.

## Run

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# optional OCR/PDF-render system tools:
# sudo apt-get install poppler-utils tesseract-ocr
streamlit run protorepair_app.py
```

Upload a PDF/DOCX/LaTeX/Markdown/text file or a scanned image from the sidebar, or paste text. The initial structured fixture remains the offline demo default.

No API key is required. To enable live extraction:

```bash
cp .env.example .env
# edit .env and set GEMINI_API_KEY
# optional: GEMINI_MODEL (default: gemini-3.5-flash-lite)
chmod 600 .env
```

The committed demo uses structured fixtures so recording and judging do not depend on the network. `EVIDENCE_MODE=none` runs the no-Valency ablation. The runtime never calls Valency.

CLI:

```bash
python -m protorepair --fixture G14
python -m protorepair --fixture G04 --json
python -m protorepair --fixture G03 --validate-patches
python -m protorepair --document protocol.pdf --json
```

## Tests

```bash
python -m pytest -q
python -m eval.protorepair.run_eval --public-only
```

The public subset reports **57 passed, 4 skipped** in this environment; the skips are live-API tests that require a key.

## Demo fixtures

Public, licensed fixtures:

- **G14** — P2-derived clean control: `READY`, no patches.
- **G02** — P2 source base: `REVIEW`; visible B1 solids/B3/C1/C2 unknowns.
- **H1–H4** — seeded P2 faults: composition/prose mismatch (B1), loading/capacity mismatch (B2), electrolyte underfill (B4), N₂ glovebox (C2).
- **Demo composite** — H1 + H3 + H4: three independent findings and three local patches.
- **G07** — P4 natural transfer case: `5.0 wt% NMP` and `3 mAh g−1` are ambiguities, not confident corrections.
- **G09** — P5 base: purchased electrode; Li-cell electrolyte volume and water values are unknown.

Three local-only source-derived fixtures are excluded from the public export. No local-only source text, example, or abstract is published.

## Patch contract

A patch is a proposal, never a merge:

- one contiguous text span, plus structured field updates used only for rerun validation;
- one finding, one patch;
- no step add/delete/reorder, no numeric score, no rewritten protocol;
- preview in the UI; applying it only re-runs the checker to show whether the target finding disappears and whether any new fail appears.

## Evaluation

```bash
python -m eval.protorepair.run_eval              # all 14 cases when local fixtures exist
python -m eval.protorepair.run_eval --public-only
```

Saved exact outputs live in `eval/protorepair/results.json` and `results.md`. The full local run reports **9 TP / 0 FP / 0 FN**, 0 value-changing patches on clean cases, 9/9 patch validity, and 14/14 readiness. The public-only run covers 11 cases and reports 7 TP / 0 FP / 0 FN, 7/7 patch validity, and 11/11 readiness. These are small descriptive counts, not a benchmark; no cells were assembled and the labels were not blind-adjudicated. The archived generic linter has no B1–B5/C1–C2 crosswalk, so it is reported as a baseline limitation, not evidence for the product. B0 (raw LLM) is marked `not_run`, not estimated.

### Live Gemini extraction (optional path)

A repeatable live run on the 11 public cases, with `gemini-3.5-flash-lite` and no cache, produced:

| Metric | Result |
|---|---:|
| Schema/quote-valid responses | 11/11 |
| Labeled faults matched | 7/7 |
| False positives / false negatives | 0 / 0 |
| Readiness exact | 11/11 |
| Patch validity | 7/7 |
| Latency mean / median / p95 / max | 9.08 / 9.43 / 10.61 / 12.27 s |

This is an extraction-path test, not the B0 raw-LLM baseline. Gemini only extracts stated facts; the deterministic checks, units, patches, and readiness remain code-owned. See `eval/protorepair/gemini_live_results.md` and rerun with `python -m eval.protorepair.run_gemini_live`.

## Media

- **Cover:** [`docs/assets/protorepair-cover.png`](docs/assets/protorepair-cover.png) (1600×900).
- **Gallery card:** [`docs/assets/protorepair-gallery-card.png`](docs/assets/protorepair-gallery-card.png) (1200×1200).
- **Tutorial:** [`docs/assets/protorepair-tutorial.mp4`](docs/assets/protorepair-tutorial.mp4) (3:12, 1080p, narrated).

## Evidence

The committed snapshot is metadata-only: title, authors, year, venue, DOI link, one-line relevance. It contains no abstracts, raw Valency/MCP output, or tokens. Public findings cite at least one curated/paper item; `heuristic` findings are labeled separately.

**Evidence retrieval powered by [Valency MCP Bond](https://www.valency.io/bond/).** No Valency logo is used and no endorsement is implied.

## Data and licenses

- Code: MIT (`LICENSE`).
- Documentation and write-up: CC BY 4.0 (`LICENSE-DOCS`).
- Public fixtures are adapted from CC BY 4.0 sources; see `THIRD_PARTY.md` and the source line in each example. Changes are disclosed (condensed text, substituted commercial material, seeded faults, labeled test values).
- Local-only fixtures, planning notes, caches, and old prototypes are excluded from the public export.
- Only the public whitelist is exported; raw outputs and secrets are not published.

## Repository layout

```text
protorepair/            deterministic checks, parser, schema, patches, report, CLI
protorepair/documents.py local PDF/DOCX/image/LaTeX reader, tables, OCR
protorepair/tablefacts.py conservative table facts for the deterministic parser
protorepair_app.py      Streamlit entrypoint
protorepair/data/       evidence snapshot and optional gitignored Gemini cache
eval/protorepair/       public fixtures, gold labels, harness, saved results
tests/test_protorepair_* new tests
scripts/export_public.py clean public export + boundary scan
```

## Known limitations

- Eleven public + three local cases; no expert adjudication, no cell assembly, no statistical power.
- The deterministic parser is conservative and can leave fields unknown; the structured fixtures are the reliable demo path.
- OCR quality depends on scan resolution, language, and Tesseract availability. Table structure from scanned pages is approximate.
- Figures/charts are captured as captions and OCR labels; plotted data series are not digitized or numerically checked.
- Formula semantics are not solved: LaTeX is normalized to text, and PDF/DOCX equations are extracted as text, not re-evaluated.
- The moisture screen shows component limits separately; the 430 ppm line is a Gr/NMC622 reference warning, not an NMC811 constant.
- B0 raw-LLM baseline requires the Gemini endpoint and three scored runs. It has not been run.
- Never publish `.env` or API keys; keep `.env` at mode 600 and rotate any key that may have been exposed.
