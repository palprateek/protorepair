#!/usr/bin/env python3
"""Create the clean public ProtoRepair export and scan its boundary.

The archived generic prototype, spec.md, .scratch, .env, P1/P3 fixtures, old
tests/data/eval, caches, and raw outputs are never copied. The public export is
whitelist-based, then tested by scanning and by running the public-only eval.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PUBLIC_CASES = ["G02", "G03", "G04", "G05", "G06", "G07", "G08", "G09", "G10", "G11", "G14"]
FORBIDDEN_NAMES = {"spec.md", "app.py", ".env"}
FORBIDDEN_DIRS = {"protoprepair", "__pycache__", ".pytest_cache", ".git", ".venv", ".scratch", "cache"}


def _copy(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*FORBIDDEN_DIRS, "*.pyc", "*.pyo"))
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _public_fixture_texts() -> dict[str, str]:
    from protorepair.fixtures import load_fixture

    return {fid: load_fixture(fid).text for fid in PUBLIC_CASES}


def build(out: Path, force: bool = False) -> None:
    if out.exists():
        if not force:
            raise SystemExit(f"{out} exists; pass --force to replace it")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for src, dst in {
        "README_PROTOREPAIR.md": "README.md",
        "LICENSE": "LICENSE",
        "LICENSE-DOCS": "LICENSE-DOCS",
        "THIRD_PARTY.md": "THIRD_PARTY.md",
        "writeup.md": "writeup.md",
        "requirements-protorepair.txt": "requirements.txt",
        ".env.example": ".env.example",
        ".gitignore": ".gitignore",
        "protorepair_app.py": "protorepair_app.py",
        "scripts/build_evidence.py": "scripts/build_evidence.py",
        "scripts/export_public.py": "scripts/export_public.py",
        "docs/protorepair-flow.svg": "docs/protorepair-flow.svg",
    }.items():
        _copy(ROOT / src, out / dst)
    _copy(ROOT / "docs/assets", out / "docs/assets")
    _copy(ROOT / "protorepair", out / "protorepair")
    # The package snapshot is the runtime source; also expose the canonical
    # public data path expected by the spec.
    _copy(ROOT / "protorepair/data/evidence.json", out / "data/evidence.json")
    examples = out / "data/examples"
    examples.mkdir(parents=True, exist_ok=True)
    texts = _public_fixture_texts()
    for fid, text in texts.items():
        (examples / f"{fid}.txt").write_text(text, encoding="utf-8")
    (examples / "README.md").write_text(
        "# Public examples\n\n"
        "These are the 11 public G02-G11/G14 fixtures adapted from CC BY 4.0 sources.\n"
        "See `THIRD_PARTY.md` for source, license, and change notices. P1/P3-derived\n"
        "fixtures are local-only and are not included.\n",
        encoding="utf-8",
    )
    # New tests only; old tests are intentionally excluded.
    test_out = out / "tests"
    test_out.mkdir()
    for p in sorted((ROOT / "tests").glob("test_protorepair_*.py")):
        shutil.copy2(p, test_out / p.name)
    # Public eval subset only.
    eval_out = out / "eval/protorepair"
    (eval_out / "cases").mkdir(parents=True)
    shutil.copy2(ROOT / "eval/protorepair/__init__.py", eval_out / "__init__.py")
    shutil.copy2(ROOT / "eval/protorepair/run_eval.py", eval_out / "run_eval.py")
    shutil.copy2(ROOT / "eval/protorepair/gold.jsonl", eval_out / "gold.jsonl")
    for name in ("gemini_live_results.json", "gemini_live_results.md", "run_gemini_live.py"):
        shutil.copy2(ROOT / "eval/protorepair" / name, eval_out / name)
    for fid in PUBLIC_CASES:
        shutil.copy2(ROOT / "eval/protorepair/cases" / f"{fid}.txt", eval_out / "cases" / f"{fid}.txt")


def scan(out: Path) -> list[str]:
    problems: list[str] = []
    files = [p for p in out.rglob("*") if p.is_file()]
    for p in files:
        rel = p.relative_to(out)
        if p.name in FORBIDDEN_NAMES or any(part in FORBIDDEN_DIRS for part in rel.parts):
            problems.append(f"forbidden path: {rel}")
        text = ""
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            pass
        if p.suffix == ".json":
            try:
                data = json.loads(text)
            except Exception:
                continue
            if isinstance(data, dict):
                for item in data.values():
                    if isinstance(item, dict) and ("abstract" in item or "raw" in item):
                        problems.append(f"evidence item has abstract/raw field: {rel}")
        if re.search(r"AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9]{20,}", text):
            problems.append(f"possible secret in {rel}")
        if "BEGIN " + "PRIVATE KEY" in text:
            problems.append(f"private key marker in {rel}")
    # Exact local P1/P3 text must never appear.
    try:
        from protorepair.fixtures import _load_local
        for fid, recipe in _load_local().items():
            for p in files:
                try:
                    if recipe.text and recipe.text in p.read_text(encoding="utf-8"):
                        problems.append(f"local-only {fid} text appears in {p.relative_to(out)}")
                except (UnicodeDecodeError, OSError):
                    pass
    except Exception:
        pass
    # Exact live key must not appear. Never print it.
    env = ROOT / ".env"
    if env.exists():
        m = re.search(r"^GEMINI_API_KEY=(.+)$", env.read_text(encoding="utf-8"), re.M)
        if m:
            key = m.group(1).strip().strip('"').strip("'")
            if key and key != "":
                for p in files:
                    try:
                        if key in p.read_text(encoding="utf-8"):
                            problems.append(f"live GEMINI_API_KEY appears in {p.relative_to(out)}")
                    except (UnicodeDecodeError, OSError):
                        pass
    return sorted(set(problems))


def _clean_caches(out: Path) -> None:
    for p in list(out.rglob("__pycache__")):
        shutil.rmtree(p, ignore_errors=True)
    shutil.rmtree(out / ".pytest_cache", ignore_errors=True)


def run_public_checks(out: Path) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(out)
    subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=out, env=env, check=True)
    subprocess.run([sys.executable, "-m", "eval.protorepair.run_eval", "--public-only"], cwd=out, env=env, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("/tmp/opencode/protorepair-public"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-test", action="store_true")
    args = ap.parse_args()
    build(args.out, force=args.force)
    if not args.no_test:
        run_public_checks(args.out)
    _clean_caches(args.out)
    problems = scan(args.out)
    if problems:
        print("PUBLIC BOUNDARY FAILED", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"Public export ready: {args.out}")
    print(f"Boundary scan passed; {sum(1 for p in args.out.rglob('*') if p.is_file())} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
