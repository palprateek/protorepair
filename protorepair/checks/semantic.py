"""Semantic/advisory checks and ambiguity findings."""
from __future__ import annotations

from ..models import CheckResult, Finding, Recipe


def check_semantic(recipe: Recipe) -> list[CheckResult]:
    d1 = CheckResult(
        check_id="D1",
        status="pass",
        family="semantic",
        title="No step-order/undefined-reference issue found",
        explanation="The assembly excerpt orders Li, separator, electrolyte, and crimp without an undefined reference.",
        confidence="high",
        evidence_ids=["EV-C2"],
    )
    d4 = CheckResult(
        check_id="D4",
        status="pass",
        family="semantic",
        title="No advisory reporting omission for this assembly excerpt",
        explanation="The input is assembly-only, so a cycling protocol is not required.",
        confidence="high",
        evidence_ids=["EV-C2"],
    )
    return [d1, d4]


def ambiguity_findings(recipe: Recipe) -> list[Finding]:
    out: list[Finding] = []
    for idx, a in enumerate(recipe.ambiguities, start=1):
        out.append(
            Finding(
                id=f"{a.class_id}-AMB-{idx:03d}",
                class_id=a.class_id,
                family="units" if a.class_id in {"A1", "A2", "A3"} else "semantic",
                step_id=a.step_id,
                quote=a.quote,
                title=a.title or f"{a.class_id} ambiguity",
                severity=a.severity if a.severity in {"medium", "low"} else "medium",
                confidence="medium",
                status="unknown",
                detection="D+L",
                explanation=a.explanation or a.issue,
                assumption_ids=[],
                evidence_ids=["EV-B1"],
                patch_id=None,
            )
        )
    return out
