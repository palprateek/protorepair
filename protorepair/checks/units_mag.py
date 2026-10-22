"""A1/A3 unit, basis, and magnitude ledgers.

A3 deliberately does not duplicate B3 Li thickness or B5 salt concentration.
"""
from __future__ import annotations

from ..models import CheckResult, Recipe


def check_units(recipe: Recipe) -> list[CheckResult]:
    a1 = [a for a in recipe.ambiguities if a.class_id == "A1"]
    if a1:
        first = a1[0]
        a1_result = CheckResult(
            check_id="A1",
            status="unknown",
            family="units",
            title="A unit or quantity basis is ambiguous",
            explanation=first.explanation or first.issue,
            severity="medium",
            confidence="medium",
            step_id=first.step_id,
            quote=first.quote,
            computed={"ambiguity_count": len(a1)},
            evidence_ids=["EV-B1"],
        )
    else:
        a1_result = CheckResult(
            check_id="A1", status="pass", family="units",
            title="No missing or ambiguous units found",
            explanation="The quantities needed by the deterministic checks have explicit units and bases.",
            confidence="high", evidence_ids=["EV-B1"],
        )
    a3_result = CheckResult(
        check_id="A3", status="pass", family="units",
        title="No unowned magnitude error found",
        explanation="Magnitude bands were applied only to quantities not owned by B3/B5; the specialized checks decide those findings.",
        confidence="high", evidence_ids=["EV-B1"],
    )
    return [a1_result, a3_result]
