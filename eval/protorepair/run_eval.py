"""Evaluation harness for the frozen 14-case ProtoRepair gold set.

Public cases are G02-G11 and G14. G01/G12/G13 are loaded from the private
.scratch harness when present; their text is never copied into public results.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from protorepair.evidence import load_evidence  # noqa: E402
from protorepair.fixtures import fixture_ids, load_fixture  # noqa: E402
from protorepair.pipeline import run_pipeline, validate_patch  # noqa: E402

PUBLIC_CASES = ["G02", "G03", "G04", "G05", "G06", "G07", "G08", "G09", "G10", "G11", "G14"]
LOCAL_CASES = ["G01", "G12", "G13"]
EXPECTED = {
    "G01": {"readiness": "NOT READY", "fail": ["C2"], "ambiguous": [], "unknown": []},
    "G02": {"readiness": "REVIEW", "fail": [], "ambiguous": [], "unknown": ["B1", "B3", "C1", "C2"]},
    "G03": {"readiness": "NOT READY", "fail": ["B1"], "ambiguous": [], "unknown": []},
    "G04": {"readiness": "NOT READY", "fail": ["B2"], "ambiguous": [], "unknown": []},
    "G05": {"readiness": "REVIEW", "fail": ["B4"], "ambiguous": [], "unknown": []},
    "G06": {"readiness": "NOT READY", "fail": ["C2"], "ambiguous": [], "unknown": []},
    "G07": {"readiness": "REVIEW", "fail": [], "ambiguous": ["A1", "A2"], "unknown": []},
    "G08": {"readiness": "NOT READY", "fail": ["B3"], "ambiguous": [], "unknown": []},
    "G09": {"readiness": "REVIEW", "fail": [], "ambiguous": [], "unknown": ["B4", "C1"]},
    "G10": {"readiness": "NOT READY", "fail": ["C1"], "ambiguous": [], "unknown": []},
    "G11": {"readiness": "NOT READY", "fail": ["B5"], "ambiguous": [], "unknown": []},
    "G12": {"readiness": "NOT READY", "fail": ["C2"], "ambiguous": [], "unknown": []},
    "G13": {"readiness": "READY", "fail": [], "ambiguous": [], "unknown": []},
    "G14": {"readiness": "READY", "fail": [], "ambiguous": [], "unknown": []},
}
CLEAN = {"G02", "G07", "G09", "G13", "G14"}


def gold_rows() -> list[dict]:
    rows = []
    public = ROOT / "eval/protorepair/gold.jsonl"
    if public.exists():
        rows += [json.loads(line) for line in public.read_text(encoding="utf-8").splitlines() if line.strip()]
    local = ROOT / ".scratch/protorepair/implementation/gold_local.jsonl"
    if local.exists():
        rows += [json.loads(line) for line in local.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows


def _evaluate_case(fid: str, evidence_mode: str | None) -> dict:
    t0 = time.perf_counter()
    result = run_pipeline(fixture_id=fid, evidence_mode=evidence_mode)
    elapsed = time.perf_counter() - t0
    pred_fail = [f.class_id for f in result.findings if f.status == "fail"]
    pred_amb = [f.class_id for f in result.findings if f.status == "unknown" and f.class_id in {"A1", "A2"}]
    pred_unknown = [f.class_id for f in result.findings if f.status == "unknown"]
    exp = EXPECTED[fid]
    gold_fail = set(exp["fail"])
    pred_fail_set = set(pred_fail)
    tp = len(gold_fail & pred_fail_set)
    fp = len(pred_fail_set - gold_fail)
    fn = len(gold_fail - pred_fail_set)
    amb_hit = len(set(exp["ambiguous"]) & set(pred_amb))
    unknown_hit = len(set(exp["unknown"]) & set(pred_unknown))
    patches = list(result.patches)
    validity = []
    for patch in patches:
        v = validate_patch(result, patch)
        validity.append({
            "patch_id": patch.id,
            "applied": v.get("applied", False),
            "target_removed": v.get("target_removed", False),
            "regressions": v.get("regressions", []),
        })
    value_patches = [p for p in patches if p.field_updates and not p.manual_fix]
    snapshot = load_evidence(evidence_mode)
    coverage = 0
    for f in result.findings:
        if f.status == "fail" and any(eid in snapshot for eid in f.evidence_ids):
            coverage += 1
    fail_count = sum(1 for f in result.findings if f.status == "fail")
    return {
        "case_id": fid,
        "public": fid in PUBLIC_CASES,
        "readiness_expected": exp["readiness"],
        "readiness_got": result.readiness,
        "readiness_match": result.readiness == exp["readiness"],
        "gold_fail": sorted(gold_fail),
        "pred_fail": sorted(pred_fail_set),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "ambiguous_expected": exp["ambiguous"],
        "ambiguous_pred": sorted(set(pred_amb)),
        "ambiguous_hit": amb_hit,
        "unknown_expected": exp["unknown"],
        "unknown_pred": sorted(set(pred_unknown)),
        "unknown_hit": unknown_hit,
        "value_patch_count": len(value_patches),
        "patch_validity": validity,
        "citation_coverage": f"{coverage}/{fail_count}" if fail_count else "n/a",
        "citation_coverage_n": coverage,
        "fail_count": fail_count,
        "latency_s": round(elapsed, 4),
        "finding_count": len(result.findings),
        "patches": [p.id for p in patches],
    }


def aggregate(cases: list[dict]) -> dict:
    tp = sum(c["tp"] for c in cases)
    fp = sum(c["fp"] for c in cases)
    fn = sum(c["fn"] for c in cases)
    patch_rows = [v for c in cases for v in c["patch_validity"]]
    valid = sum(1 for v in patch_rows if v["target_removed"] and not v["regressions"])
    clean_cases = [c for c in cases if c["case_id"] in CLEAN]
    clean_value_patches = sum(c["value_patch_count"] for c in clean_cases)
    amb_total = sum(len(c["ambiguous_expected"]) for c in cases)
    amb_hit = sum(c["ambiguous_hit"] for c in cases)
    unknown_total = sum(len(c["unknown_expected"]) for c in cases)
    unknown_hit = sum(c["unknown_hit"] for c in cases)
    fail_findings = sum(c["fail_count"] for c in cases)
    coverage = sum(c["citation_coverage_n"] for c in cases)
    return {
        "cases": len(cases),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "clean_value_patches": clean_value_patches,
        "clean_false_patch_rate": round(clean_value_patches / len(clean_cases), 4) if clean_cases else None,
        "patches_tested": len(patch_rows),
        "patch_validity": round(valid / len(patch_rows), 4) if patch_rows else None,
        "no_regression": round(
            sum(1 for v in patch_rows if not v["regressions"]) / len(patch_rows), 4
        ) if patch_rows else None,
        "citation_coverage": round(coverage / fail_findings, 4) if fail_findings else None,
        "citation_n": f"{coverage}/{fail_findings}",
        "ambiguity_recall": round(amb_hit / amb_total, 4) if amb_total else None,
        "unknown_recall": round(unknown_hit / unknown_total, 4) if unknown_total else None,
        "readiness_exact": f"{sum(1 for c in cases if c['readiness_match'])}/{len(cases)}",
        "critical_ready_errors": sum(
            1 for c in cases if c["readiness_expected"] in {"NOT READY", "REVIEW"} and c["readiness_got"] == "READY"
        ),
    }


def archived_linter(cases: list[str]) -> dict:
    """Run the archived generic linter unchanged; map nothing because it has no taxonomy rule IDs for these cases."""
    if not (ROOT / "protoprepair").exists():
        return {
            "status": "not_run",
            "rows": [],
            "notes": "Archived generic linter is excluded from the public export; no baseline was run there.",
        }
    rows = []
    for fid in cases:
        path = ROOT / "eval/protorepair/cases" / f"{fid}.txt"
        if not path.exists():
            continue
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "protoprepair", str(path), "--json"],
                cwd=ROOT, capture_output=True, text=True, timeout=30,
            )
            payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
            findings = payload.get("findings", []) or payload.get("issues", [])
            rows.append({"case_id": fid, "returncode": proc.returncode, "findings": findings, "mapped_fail": []})
        except Exception as exc:
            rows.append({"case_id": fid, "error": str(exc), "mapped_fail": []})
    # No archived rule maps to B1-B5/C1-C2; every gold fail is therefore an FN.
    tp = 0
    fp = 0
    fn = sum(len(EXPECTED[fid]["fail"]) for fid in cases if fid in EXPECTED)
    return {
        "status": "ran",
        "rows": rows,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": None,
        "recall": 0.0 if fn else None,
        "readiness_exact": "not comparable",
        "notes": "Archived generic linter has no B1-B5/C1-C2 taxonomy; no crosswalk match, so all gold fails are FN. It is not tuned.",
    }


def run(public_only: bool = False, evidence_mode: str | None = None) -> dict:
    ids = PUBLIC_CASES if public_only else [f for f in PUBLIC_CASES + LOCAL_CASES if f in fixture_ids(public_only=False)]
    cases = [_evaluate_case(fid, evidence_mode) for fid in ids]
    full = aggregate(cases)
    b2_cases = [_evaluate_case(fid, evidence_mode) for fid in ids]
    b2 = aggregate(b2_cases)
    b4_cases = [_evaluate_case(fid, "none") for fid in ids]
    b4 = aggregate(b4_cases)
    b3 = archived_linter([fid for fid in ids if fid in PUBLIC_CASES])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_ids": ids,
        "gold_rows": len(gold_rows()),
        "systems": {
            "protorepair_full": full,
            "b0_structured_raw_llm": {
                "status": "not_run",
                "notes": "B0 requires the Gemini endpoint and three scored runs; it is not silently substituted. Run with --b0 when the key/network are available.",
            },
            "b1_free_text_raw_llm": {"status": "not_run", "notes": "Optional; not run before B0."},
            "b2_deterministic_only": b2,
            "b3_archived_linter": b3,
            "b4_no_valency": b4,
        },
        "cases": cases,
    }


def render_md(results: dict) -> str:
    s = results["systems"]
    lines = [
        "# ProtoRepair evaluation results",
        "",
        f"Generated: `{results['generated_at']}`",
        "",
        f"Small descriptive case study; {results['systems']['protorepair_full']['cases']} cases, "
        f"{sum(len(c['gold_fail']) for c in results['cases'])} fail labels, "
        f"{sum(1 for c in results['cases'] if c['readiness_expected'] == 'READY')} fully specified clean control(s). "
        f"No statistical-power claim.",
        "",
        "## Table 1 — Overall",
        "",
        "| System | TP | FP | FN | Precision | Recall | Clean value patches | Patch validity | No-regression | Citation coverage | Readiness exact |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, label in [
        ("protorepair_full", "ProtoRepair full"),
        ("b0_structured_raw_llm", "B0 structured raw LLM"),
        ("b1_free_text_raw_llm", "B1 free-text raw LLM"),
        ("b2_deterministic_only", "B2 deterministic-only"),
        ("b3_archived_linter", "B3 archived generic linter"),
        ("b4_no_valency", "B4 no-Valency"),
    ]:
        v = s[key]
        if v.get("status") == "not_run":
            lines.append(f"| {label} | — | — | — | — | — | — | — | — | — | — |")
            continue
        lines.append(
            f"| {label} | {v.get('tp','—')} | {v.get('fp','—')} | {v.get('fn','—')} | "
            f"{v.get('precision','—')} | {v.get('recall','—')} | {v.get('clean_value_patches','—')} | "
            f"{v.get('patch_validity','—')} | {v.get('no_regression','—')} | {v.get('citation_coverage','—')} | {v.get('readiness_exact','—')} |"
        )
    lines += ["", "## Table 2 — Per case", "", "| Case | Public | Gold fail | Pred fail | TP | FP | FN | Patches | Readiness exp/got | Findings |", "|---|---:|---|---|---:|---:|---:|---|---|---:|"]
    for c in results["cases"]:
        lines.append(
            f"| {c['case_id']} | {'yes' if c['public'] else 'local-only'} | {', '.join(c['gold_fail']) or '—'} | "
            f"{', '.join(c['pred_fail']) or '—'} | {c['tp']} | {c['fp']} | {c['fn']} | "
            f"{', '.join(c['patches']) or '—'} | {c['readiness_expected']} / {c['readiness_got']} | {c['finding_count']} |"
        )
    lines += [
        "",
        "## Notes and limits",
        "",
        "- B2 here is the deterministic-only path; the full fixture path also uses structured facts because the demo cache is intentional.",
        ("- B3 was run unchanged on public cases; it has no B1-B5/C1-C2 crosswalk, so every gold fail is an FN and no TP is claimed."
         if s["b3_archived_linter"].get("status") != "not_run" else
         "- B3 is marked not_run in this export; the archived generic linter is intentionally excluded from the public artifact."),
        "- B4 uses `EVIDENCE_MODE=none`; findings are unchanged and citation coverage falls to zero by construction.",
        "- B0 was not run in this environment; the system is marked not_run rather than estimated.",
        "- G01/G12/G13 are local-only and not publicly reproducible; no local text is included in this report.",
        "- Patches are evaluated by applying the text/structured patch and rerunning all checks. No cells were assembled.",
        "",
        "Allowed headline: "
        f"“On {results['systems']['protorepair_full']['cases']} small cases, ProtoRepair matched "
        f"{results['systems']['protorepair_full']['tp']}/{sum(len(c['gold_fail']) for c in results['cases'])} labeled faults with "
        f"{results['systems']['protorepair_full']['fp']} false positives; on "
        f"{sum(1 for c in results['cases'] if c['readiness_expected'] == 'READY')} fully specified clean control(s) it emitted "
        f"{results['systems']['protorepair_full']['clean_value_patches']} value-changing patches; "
        f"{results['systems']['protorepair_full']['patches_tested']} proposed patches were tested.”",
        "",
        "This is descriptive only. It is not a benchmark, not expert-reviewed, and not a safety certification.",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--public-only", action="store_true")
    ap.add_argument("--evidence-mode", default=None)
    ap.add_argument("--out", default=str(ROOT / "eval/protorepair/results"))
    args = ap.parse_args()
    results = run(public_only=args.public_only, evidence_mode=args.evidence_mode)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "protorepair.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (out.parent / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    md = render_md(results)
    (out.parent / "results.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
