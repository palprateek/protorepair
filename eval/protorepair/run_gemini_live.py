"""Live Gemini extraction check for the public ProtoRepair case set.

This is an optional extraction-path evaluation, not the deterministic gold
evaluation. It writes only case IDs, counts, latencies, and validation status;
it never writes protocol text, prompts, raw model output, or the API key.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from protorepair.extract import MODEL, extract  # noqa: E402
from protorepair.fixtures import load_fixture  # noqa: E402
from protorepair.pipeline import run_pipeline, validate_patch  # noqa: E402
from eval.protorepair.run_eval import EXPECTED, LOCAL_CASES, PUBLIC_CASES  # noqa: E402

DEFAULT_JSON = Path(__file__).with_name("gemini_live_results.json")
DEFAULT_MD = Path(__file__).with_name("gemini_live_results.md")


def _case_ids(include_local: bool) -> list[str]:
    ids = list(PUBLIC_CASES)
    if include_local:
        for fid in LOCAL_CASES:
            try:
                load_fixture(fid)
                ids.append(fid)
            except KeyError:
                pass
    return ids


def _run_one(fid: str, use_cache: bool) -> dict:
    base = load_fixture(fid)
    started = time.perf_counter()
    outcome = extract(base.text, recipe=base, use_cache=use_cache)
    wall = time.perf_counter() - started
    result = run_pipeline(recipe=outcome.recipe, extraction_mode=outcome.mode)
    expected = EXPECTED[fid]
    gold_fail = sorted(expected["fail"])
    pred_fail = sorted({f.class_id for f in result.findings if f.status == "fail"})
    patches = []
    for patch in result.patches:
        validation = validate_patch(result, patch)
        patches.append({
            "id": patch.id,
            "applied": bool(validation.get("applied")),
            "target_removed": bool(validation.get("target_removed")),
            "new_fail_classes": validation.get("new_fail_classes", []),
            "error": validation.get("error"),
        })
    return {
        "case": fid,
        "extraction_mode": outcome.mode,
        "cached": outcome.cached,
        "latency_s": round(wall, 3),
        "validation_errors": len(outcome.errors),
        "readiness_expected": expected["readiness"],
        "readiness": result.readiness,
        "gold_fail": gold_fail,
        "pred_fail": pred_fail,
        "tp": len(set(gold_fail) & set(pred_fail)),
        "fp": len(set(pred_fail) - set(gold_fail)),
        "fn": len(set(gold_fail) - set(pred_fail)),
        "unknown": sorted({f.class_id for f in result.findings if f.status == "unknown"}),
        "patches": patches,
    }


def _aggregate(cases: list[dict]) -> dict:
    latencies = [c["latency_s"] for c in cases]
    tested = sum(len(c["patches"]) for c in cases)
    valid = sum(
        1 for c in cases for p in c["patches"]
        if p["applied"] and p["target_removed"] and not p["new_fail_classes"]
    )
    return {
        "cases": len(cases),
        "api_ok": sum(1 for c in cases if c["validation_errors"] == 0),
        "validation_errors": sum(c["validation_errors"] for c in cases),
        "tp": sum(c["tp"] for c in cases),
        "fp": sum(c["fp"] for c in cases),
        "fn": sum(c["fn"] for c in cases),
        "readiness_exact": sum(1 for c in cases if c["readiness"] == c["readiness_expected"]),
        "patches_tested": tested,
        "patches_valid": valid,
        "latency_mean_s": round(statistics.mean(latencies), 3) if latencies else None,
        "latency_median_s": round(statistics.median(latencies), 3) if latencies else None,
        "latency_max_s": round(max(latencies), 3) if latencies else None,
        "latency_p95_s": round(sorted(latencies)[max(0, int(0.95 * (len(latencies) - 1)))], 3) if latencies else None,
    }


def render_md(results: dict) -> str:
    s = results["summary"]
    lines = [
        "# Live Gemini extraction results",
        "",
        f"Generated: `{results['generated_at']}`",
        f"Model: `{results['model']}` · cases: `{s['cases']}` · cache: `{results['use_cache']}`",
        "",
        "Optional extraction path. Deterministic checks, units, patches, and readiness remain code-owned.",
        "No protocol text, prompts, raw model output, or credentials are included in this report.",
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Schema/quote-valid responses | {s['api_ok']}/{s['cases']} |",
        f"| Labeled faults matched | {s['tp']}/{sum(len(c['gold_fail']) for c in results['cases'])} |",
        f"| False positives | {s['fp']} |",
        f"| False negatives | {s['fn']} |",
        f"| Readiness exact | {s['readiness_exact']}/{s['cases']} |",
        f"| Patch validity | {s['patches_valid']}/{s['patches_tested']} |",
        f"| Latency mean / median / p95 / max | {s['latency_mean_s']} / {s['latency_median_s']} / {s['latency_p95_s']} / {s['latency_max_s']} s |",
        "",
        "## Per case",
        "",
        "| Case | Mode | Latency | Gold fail | Pred fail | TP | FP | FN | Readiness exp/got | Patches valid |",
        "|---|---|---:|---|---|---:|---:|---:|---|---|",
    ]
    for c in results["cases"]:
        patch_ok = sum(1 for p in c["patches"] if p["applied"] and p["target_removed"] and not p["new_fail_classes"])
        lines.append(
            f"| {c['case']} | {c['extraction_mode']} | {c['latency_s']:.2f}s | "
            f"{', '.join(c['gold_fail']) or '—'} | {', '.join(c['pred_fail']) or '—'} | "
            f"{c['tp']} | {c['fp']} | {c['fn']} | {c['readiness_expected']} / {c['readiness']} | "
            f"{patch_ok}/{len(c['patches'])} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- This run uses the optional Gemini extraction path; the structured fixture path is separately evaluated.",
        "- Patch validity means the patch applies, removes its target fail, and adds no new fail on rerun.",
        "- Extraction is untrusted: every response must pass JSON Schema and quote/line validation or is discarded.",
        "- The model is not asked to calculate checks; it only extracts stated facts.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="include local-only cases when available")
    parser.add_argument("--cache", action="store_true", help="reuse validated extraction cache")
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD)
    args = parser.parse_args(argv)

    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set; live extraction not run.")
        return 2

    case_ids = _case_ids(args.all)
    cases = [_run_one(fid, use_cache=args.cache) for fid in case_ids]
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "use_cache": args.cache,
        "summary": _aggregate(cases),
        "cases": cases,
    }
    args.json_out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    args.md_out.write_text(render_md(results), encoding="utf-8")
    s = results["summary"]
    print(
        f"cases={s['cases']} api_ok={s['api_ok']} tp={s['tp']} fp={s['fp']} fn={s['fn']} "
        f"readiness={s['readiness_exact']}/{s['cases']} patches={s['patches_valid']}/{s['patches_tested']} "
        f"mean={s['latency_mean_s']}s"
    )
    print(f"wrote {args.json_out} and {args.md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
