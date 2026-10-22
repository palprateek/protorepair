"""Deterministic text pre-parser: line IDs, headings, steps, and tables."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Step


@dataclass
class ParsedText:
    raw: str
    lines: list[str]
    numbered: list[str]
    steps: list[Step]
    tables: list[list[list[str]]] = field(default_factory=list)


_STEP_START = re.compile(r"^\s*(?:step\s*)?\(?(\d{1,2})[\.\):\-]\s+", re.IGNORECASE)


def normalize_lines(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return [line.rstrip() for line in text.split("\n")]


def segment_steps(lines: list[str]) -> list[Step]:
    steps: list[Step] = []
    current: list[str] = []
    start = 0

    def flush(end: int | None = None) -> None:
        nonlocal current, start
        if not current:
            return
        text = "\n".join(current).strip()
        if text:
            steps.append(Step(step_id=f"S{len(steps) + 1}", text=text, line_start=start, line_end=end or start + len(current) - 1))
        current = []
        start = 0

    for idx, line in enumerate(lines, start=1):
        if not line.strip():
            if current:
                current.append(line)
            continue
        if _STEP_START.match(line):
            flush(idx - 1)
            current = [line.strip()]
            start = idx
        elif current:
            current.append(line.strip())
        else:
            current = [line.strip()]
            start = idx
    flush(len(lines))
    if not steps:
        nonempty = "\n".join(l.strip() for l in lines if l.strip()).strip()
        if nonempty:
            steps = [Step("S1", nonempty, 1, max(1, len(lines)))]
    return steps


def flatten_tables(lines: list[str]) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in lines:
        if "|" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            current.append(cells)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def preparse(text: str) -> ParsedText:
    lines = normalize_lines(text)
    numbered = [f"[L{i:03d}] {line}" for i, line in enumerate(lines, start=1)]
    return ParsedText(raw=text, lines=lines, numbered=numbered, steps=segment_steps(lines), tables=flatten_tables(lines))
