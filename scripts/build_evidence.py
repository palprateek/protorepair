#!/usr/bin/env python3
"""Validate and publish the committed metadata-only evidence snapshot.

Retrieval from Valency MCP Bond is a private, build-time step; this public
script deliberately performs no network call and stores no token. Pass a
metadata-only export from that private step with ``--input`` (or use the
committed snapshot) and the script validates the public boundary before writing
``data/evidence.json``.

Rejected: abstracts, full text, raw MCP/JSON payloads, prompts, and secrets.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "protorepair/data/evidence.json"
DEFAULT_OUT = ROOT / "data/evidence.json"
REQUIRED = {"id", "kind", "title", "claim"}
FORBIDDEN_KEYS = re.compile(r"abstract|full_?text|raw|content|prompt|token|secret|api_?key", re.I)
FORBIDDEN_TEXT = re.compile(r"\b(?:abstract|full text|raw mcp|api[_-]?key)\b", re.I)


def validate(items: dict) -> list[str]:
    problems: list[str] = []
    if not isinstance(items, dict):
        return ["evidence snapshot must be a JSON object keyed by evidence id"]
    for key, item in items.items():
        if not isinstance(item, dict):
            problems.append(f"{key}: not an object")
            continue
        missing = REQUIRED - set(item)
        if missing:
            problems.append(f"{key}: missing {sorted(missing)}")
        for field, value in item.items():
            if FORBIDDEN_KEYS.search(field):
                problems.append(f"{key}: forbidden field {field!r}")
            if isinstance(value, str) and FORBIDDEN_TEXT.search(value):
                problems.append(f"{key}: forbidden text in {field!r}")
        if item.get("id") != key:
            problems.append(f"{key}: id field must match key")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="validate only; do not write")
    args = ap.parse_args()
    items = json.loads(args.input.read_text(encoding="utf-8"))
    problems = validate(items)
    if problems:
        print("Evidence snapshot rejected:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    if not args.check:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Validated {len(items)} metadata-only evidence items"
        + ("" if args.check else f"; wrote {args.out}")
        + ". No network call; no abstracts or raw Valency output."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
