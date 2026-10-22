"""Load the committed metadata-only evidence snapshot.

The runtime never calls Valency. EVIDENCE_MODE=none returns an empty snapshot
for the no-Valency ablation; findings still run and fall back to curated text.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


_PATH = Path(__file__).with_name("data") / "evidence.json"


def load_evidence(mode: str | None = None) -> dict[str, dict]:
    mode = (mode or os.getenv("EVIDENCE_MODE", "full")).lower()
    if mode == "none":
        return {}
    if not _PATH.exists():
        return {}
    return json.loads(_PATH.read_text(encoding="utf-8"))


def resolve(ids: list[str], snapshot: dict[str, dict] | None = None) -> list[dict]:
    snapshot = snapshot if snapshot is not None else load_evidence()
    return [snapshot[i] for i in ids if i in snapshot]


def resolvable(ids: list[str], snapshot: dict[str, dict] | None = None) -> bool:
    return bool(resolve(ids, snapshot))


def attribution() -> str:
    return "Evidence retrieval powered by Valency MCP Bond (https://www.valency.io/bond/); metadata-only public display."
