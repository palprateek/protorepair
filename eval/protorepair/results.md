# ProtoRepair evaluation results

Generated: `2026-10-22T14:50:06.842434+00:00`

Small descriptive case study; 11 cases, 7 fail labels, 1 fully specified clean control(s). No statistical-power claim.

## Table 1 — Overall

| System | TP | FP | FN | Precision | Recall | Clean value patches | Patch validity | No-regression | Citation coverage | Readiness exact |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ProtoRepair full | 7 | 0 | 0 | 1.0 | 1.0 | 0 | 1.0 | 1.0 | 1.0 | 11/11 |
| B0 structured raw LLM | — | — | — | — | — | — | — | — | — | — |
| B1 free-text raw LLM | — | — | — | — | — | — | — | — | — | — |
| B2 deterministic-only | 7 | 0 | 0 | 1.0 | 1.0 | 0 | 1.0 | 1.0 | 1.0 | 11/11 |
| B3 archived generic linter | — | — | — | — | — | — | — | — | — | — |
| B4 no-Valency | 7 | 0 | 0 | 1.0 | 1.0 | 0 | 1.0 | 1.0 | 0.0 | 11/11 |

## Table 2 — Per case

| Case | Public | Gold fail | Pred fail | TP | FP | FN | Patches | Readiness exp/got | Findings |
|---|---:|---|---|---:|---:|---:|---|---|---:|
| G02 | yes | — | — | 0 | 0 | 0 | — | REVIEW / REVIEW | 4 |
| G03 | yes | B1 | B1 | 1 | 0 | 0 | P-B1-G03 | NOT READY / NOT READY | 4 |
| G04 | yes | B2 | B2 | 1 | 0 | 0 | P-B2-G04 | NOT READY / NOT READY | 5 |
| G05 | yes | B4 | B4 | 1 | 0 | 0 | P-B4-G05 | REVIEW / REVIEW | 5 |
| G06 | yes | C2 | C2 | 1 | 0 | 0 | P-C2-G06 | NOT READY / NOT READY | 4 |
| G07 | yes | — | — | 0 | 0 | 0 | — | REVIEW / REVIEW | 6 |
| G08 | yes | B3 | B3 | 1 | 0 | 0 | P-B3-G08 | NOT READY / NOT READY | 7 |
| G09 | yes | — | — | 0 | 0 | 0 | — | REVIEW / REVIEW | 2 |
| G10 | yes | C1 | C1 | 1 | 0 | 0 | P-C1-G10 | NOT READY / NOT READY | 2 |
| G11 | yes | B5 | B5 | 1 | 0 | 0 | P-B5-G11 | NOT READY / NOT READY | 3 |
| G14 | yes | — | — | 0 | 0 | 0 | — | READY / READY | 0 |

## Notes and limits

- B2 here is the deterministic-only path; the full fixture path also uses structured facts because the demo cache is intentional.
- B3 is marked not_run in this export; the archived generic linter is intentionally excluded from the public artifact.
- B4 uses `EVIDENCE_MODE=none`; findings are unchanged and citation coverage falls to zero by construction.
- B0 was not run in this environment; the system is marked not_run rather than estimated.
- G01/G12/G13 are local-only and not publicly reproducible; no local text is included in this report.
- Patches are evaluated by applying the text/structured patch and rerunning all checks. No cells were assembled.

Allowed headline: “On 11 small cases, ProtoRepair matched 7/7 labeled faults with 0 false positives; on 1 fully specified clean control(s) it emitted 0 value-changing patches; 7 proposed patches were tested.”

This is descriptive only. It is not a benchmark, not expert-reviewed, and not a safety certification.