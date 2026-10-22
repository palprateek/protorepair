# ProtoRepair

**Pre-flight consistency checks for NMC811 || Li-metal coin-cell protocols.**

Paste an assembly excerpt. ProtoRepair returns **findings + one local patch per finding**, backed by explicit arithmetic, units, and metadata-only evidence. It does **not** rewrite the protocol, merge a corrected version, or emit a numeric “protocol score.”

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
pip install -r requirements-protorepair.txt
streamlit run protorepair_app.py
```

No API key is required. To enable live extraction:

```bash
cp .env.example .env
# edit .env and set GEMINI_API_KEY
chmod 600 .env
```

The committed demo uses structured fixtures so recording and judging do not depend on the network. `EVIDENCE_MODE=none` runs the no-Valency ablation. The runtime never calls Valency.

CLI:

```bash
python -m protorepair --fixture G14
python -m protorepair --fixture G04 --json
python -m protorepair --fixture G03 --validate-patches
```

## Demo fixtures

Public, licensed fixtures:

- **G14** — P2-derived clean control: `READY`, no patches.
- **G02** — P2 source base: `REVIEW`; visible B1 solids/B3/C1/C2 unknowns.
- **H1–H4** — seeded P2 faults: composition/prose mismatch (B1), loading/capacity mismatch (B2), electrolyte underfill (B4), N₂ glovebox (C2).
- **Demo composite** — H1 + H3 + H4: three independent findings and three local patches.
- **G07** — P4 natural transfer case: `5.0 wt% NMP` and `3 mAh g−1` are ambiguities, not confident corrections.
- **G09** — P5 base: purchased electrode; Li-cell electrolyte volume and water values are unknown.

P1/P3-derived fixtures are **local-only** and are not in the public export. Public results mention their case IDs only to disclose that they are not publicly reproducible; no source text, example, or abstract is published.

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

Saved exact outputs live in `eval/protorepair/results.json` and `results.md`. The full local run reports **9 TP / 0 FP / 0 FN**, 0 value-changing patches on clean cases, 9/9 patch validity, and 14/14 readiness. The public-only run covers 11 cases and reports 7 TP / 0 FP / 0 FN. These are small descriptive counts, not a benchmark; no cells were assembled and the labels were not blind-adjudicated. The archived generic linter has no B1–B5/C1–C2 crosswalk, so it is reported as a baseline limitation, not evidence for the product. B0 (raw LLM) is marked `not_run`, not estimated.

## Evidence

The committed snapshot is metadata-only: title, authors, year, venue, DOI link, one-line relevance. It contains no abstracts, raw Valency/MCP output, or tokens. Public findings cite at least one curated/paper item; `heuristic` findings are labeled separately.

**Evidence retrieval powered by [Valency MCP Bond](https://www.valency.io/bond/).** No Valency logo is used and no endorsement is implied.

## Data and licenses

- Code: MIT (`LICENSE`).
- Documentation and write-up: CC BY 4.0 (`LICENSE-DOCS`).
- Public fixtures are adapted from CC BY 4.0 sources; see `THIRD_PARTY.md` and the source line in each example. Changes are disclosed (condensed text, substituted commercial material, seeded faults, labeled test values).
- P1- and P3-derived fixtures are local-only and excluded from the public export.
- `spec.md`, `.scratch/`, `.env`, caches, old `protoprepair/`, root `app.py`, old data/tests/eval, and raw outputs are not part of the public export.

## Repository layout

```text
protorepair/            deterministic checks, parser, schema, patches, report, CLI
protorepair_app.py      Streamlit entrypoint
protorepair/data/       evidence snapshot and optional gitignored Gemini cache
eval/protorepair/       public fixtures, gold labels, harness, saved results
tests/test_protorepair_* new tests
scripts/export_public.py clean public export + boundary scan
```

## Known limitations

- Eleven public + three local cases; no expert adjudication, no cell assembly, no statistical power.
- The deterministic parser is conservative and can leave fields unknown; the structured fixtures are the reliable demo path.
- The moisture screen shows component limits separately; the 430 ppm line is a Gr/NMC622 reference warning, not an NMC811 constant.
- B0 raw-LLM baseline requires the Gemini endpoint and three scored runs. It has not been run.
- The exposed planning API key must be rotated after the hackathon; never publish `.env`.
