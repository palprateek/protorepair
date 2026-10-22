# Live Gemini extraction results

Generated: `2026-10-22T10:39:02.039518+00:00`
Model: `gemini-3.5-flash-lite` · cases: `11` · cache: `False`

Optional extraction path. Deterministic checks, units, patches, and readiness remain code-owned.
No protocol text, prompts, raw model output, or credentials are included in this report.

## Summary

| Metric | Result |
|---|---:|
| Schema/quote-valid responses | 11/11 |
| Labeled faults matched | 7/7 |
| False positives | 0 |
| False negatives | 0 |
| Readiness exact | 11/11 |
| Patch validity | 7/7 |
| Latency mean / median / p95 / max | 9.084 / 9.431 / 10.612 / 12.274 s |

## Per case

| Case | Mode | Latency | Gold fail | Pred fail | TP | FP | FN | Readiness exp/got | Patches valid |
|---|---|---:|---|---|---:|---:|---:|---|---|
| G02 | gemini | 10.15s | — | — | 0 | 0 | 0 | REVIEW / REVIEW | 0/0 |
| G03 | gemini | 9.43s | B1 | B1 | 1 | 0 | 0 | NOT READY / NOT READY | 1/1 |
| G04 | gemini | 12.27s | B2 | B2 | 1 | 0 | 0 | NOT READY / NOT READY | 1/1 |
| G05 | gemini | 9.92s | B4 | B4 | 1 | 0 | 0 | REVIEW / REVIEW | 1/1 |
| G06 | gemini | 10.51s | C2 | C2 | 1 | 0 | 0 | NOT READY / NOT READY | 1/1 |
| G07 | gemini | 8.03s | — | — | 0 | 0 | 0 | REVIEW / REVIEW | 0/0 |
| G08 | gemini | 8.43s | B3 | B3 | 1 | 0 | 0 | NOT READY / NOT READY | 1/1 |
| G09 | gemini | 6.57s | — | — | 0 | 0 | 0 | REVIEW / REVIEW | 0/0 |
| G10 | gemini | 6.92s | C1 | C1 | 1 | 0 | 0 | NOT READY / NOT READY | 1/1 |
| G11 | gemini | 7.08s | B5 | B5 | 1 | 0 | 0 | NOT READY / NOT READY | 1/1 |
| G14 | gemini | 10.61s | — | — | 0 | 0 | 0 | READY / READY | 0/0 |

## Notes

- This run uses the optional Gemini extraction path; the structured fixture path is separately evaluated.
- Patch validity means the patch applies, removes its target fail, and adds no new fail on rerun.
- Extraction is untrusted: every response must pass JSON Schema and quote/line validation or is discarded.
- The model is not asked to calculate checks; it only extracts stated facts.
