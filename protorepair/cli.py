"""Command-line entry point for deterministic checks and demo fixtures."""
from __future__ import annotations

import argparse
import sys

from .fixtures import fixture_ids, load_fixture
from .pipeline import run_pipeline, validate_patch
from .report import to_json, to_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="protorepair")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--fixture", choices=fixture_ids(public_only=False))
    src.add_argument("--text", help="path to a protocol text file")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--validate-patches", action="store_true")
    parser.add_argument("--evidence-mode", default=None)
    args = parser.parse_args(argv)

    if args.fixture:
        result = run_pipeline(fixture_id=args.fixture, evidence_mode=args.evidence_mode)
    else:
        text = open(args.text, encoding="utf-8").read()
        result = run_pipeline(text=text, evidence_mode=args.evidence_mode)

    if args.validate_patches:
        for patch in result.patches:
            v = validate_patch(result, patch)
            print(f"{patch.id}: applied={v['applied']} target_removed={v['target_removed']} regressions={v['regressions']}")
    print(to_json(result) if args.json else to_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
