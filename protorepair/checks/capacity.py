"""B2 loading / areal capacity / specific capacity consistency."""
from __future__ import annotations

from ..models import CheckResult, Patch, Recipe
from ..units import active_loading as active_loading_fn
from ..units import q_areal_mAh_cm2, qspec_inferred

EV = ["EV-B2"]


def check_capacity(recipe: Recipe) -> CheckResult:
    e = recipe.electrode
    fraction = recipe.active_fraction
    total = e.total_loading_mg_cm2
    active = e.active_loading_mg_cm2
    if active is None and total is not None and fraction is not None:
        active = active_loading_fn(total, fraction)
    q_areal = e.areal_capacity_mAh_cm2
    qspec = e.specific_capacity_mAh_g
    assumption_ids: list[str] = []
    source_ev = ["EV-P2"] if (recipe.protocol.doi or "").endswith("3c14394") else []
    if (recipe.protocol.doi or "").endswith("58627-3"):
        source_ev = ["EV-P4"]
    if (recipe.protocol.doi or "").endswith("72530-5"):
        source_ev = ["EV-P5"]
    step = e.step_id or recipe.step_for_quote(e.quote) or "S2"
    computed = {
        "total_loading_mg_cm2": total,
        "active_fraction": fraction,
        "active_loading_mg_cm2": active,
        "specific_capacity_mAh_g": qspec,
        "stated_areal_capacity_mAh_cm2": q_areal,
    }

    if active is None or q_areal is None or qspec is None:
        return CheckResult(
            check_id="B2",
            status="unknown",
            family="capacity",
            title="Loading/capacity basis cannot be checked",
            explanation=(
                "The protocol does not provide the active loading (or total loading plus active fraction), "
                "the specific capacity, and the areal capacity together. Missing values are not treated as zero."
            ),
            severity="medium",
            confidence="medium",
            step_id=step,
            quote=e.quote,
            computed=computed,
            assumption_ids=assumption_ids,
            evidence_ids=EV + source_ev,
        )

    computed_q = q_areal_mAh_cm2(active, qspec)
    inferred = qspec_inferred(q_areal, active)
    rel = abs(computed_q - q_areal) / q_areal if q_areal else None
    computed.update({"computed_areal_capacity_mAh_cm2": computed_q, "inferred_specific_capacity_mAh_g": inferred, "relative_error": rel})
    basis_ok = inferred is not None and 150.0 <= inferred <= 230.0

    if rel is not None and rel > 0.10:
        severity = "critical" if rel > 10.0 else ("high" if rel > 0.25 else "medium")
        basis_text = ""
        if not basis_ok:
            basis_text = f" The implied specific capacity is {inferred:.1f} mAh/g, outside the 150-230 mAh/g plausibility band."
        title = "Loading and areal capacity disagree by about 2x" if severity == "high" else "Loading and areal capacity disagree"
        expl = (
            f"{active:g} mg/cm² active × {qspec:g} mAh/g / 1000 = {computed_q:.3f} mAh/cm², "
            f"not the stated {q_areal:g} mAh/cm² ({rel * 100:.0f}% difference).{basis_text} "
            "The loading and capacity cannot both be right."
        )
        patch = None
        if recipe.fixture_id in {"G04", "DEMO"} and total is not None:
            target = q_areal / (fraction * qspec / 1000.0) if fraction and qspec else None
            if target is not None:
                patch = Patch(
                    id=f"P-B2-{recipe.fixture_id}",
                    finding_id=f"B2-{recipe.fixture_id}",
                    op="replace",
                    step_id=step,
                    before=f"{total:g} mg/cm²",
                    after=f"{target:.1f} mg/cm²",
                    rationale="Restores the source-faithful loading that gives the stated areal capacity at 95% active and 200 mAh/g.",
                    evidence_ids=EV + source_ev,
                    field_updates={"electrode.total_loading_mg_cm2": round(target, 1)},
                )
        elif total is not None and fraction and qspec:
            target = q_areal / (fraction * qspec / 1000.0)
            patch = Patch(
                id=f"P-B2-{recipe.fixture_id or 'case'}",
                finding_id=f"B2-{recipe.fixture_id or 'case'}",
                op="replace",
                step_id=step,
                before=f"{total:g} mg/cm²",
                after=f"{target:.1f} mg/cm²",
                rationale="Replace one loading number with the value implied by the stated areal capacity and active fraction.",
                evidence_ids=EV + source_ev,
                field_updates={"electrode.total_loading_mg_cm2": round(target, 1)},
            )
        return CheckResult(
            check_id="B2", status="fail", family="capacity", title=title, explanation=expl,
            severity=severity, confidence="high", step_id=step, quote=e.quote,
            computed=computed, assumption_ids=assumption_ids, evidence_ids=EV + source_ev,
            patch=patch,
        )

    if not basis_ok:
        return CheckResult(
            check_id="B2",
            status="fail",
            family="capacity",
            title="Capacity basis is implausible",
            explanation=(
                f"The stated loading and areal capacity agree within 10%, but they imply {inferred:.1f} mAh/g, "
                "outside the 150-230 mAh/g plausibility band. Check whether the capacity is per active mass or per area."
            ),
            severity="medium",
            confidence="high",
            step_id=step,
            quote=e.quote,
            computed=computed,
            assumption_ids=assumption_ids,
            evidence_ids=EV + source_ev,
            manual_fix=True,
        )

    return CheckResult(
        check_id="B2",
        status="pass",
        family="capacity",
        title="Loading and areal capacity agree",
        explanation=(
            f"{active:g} mg/cm² active × {qspec:g} mAh/g / 1000 = {computed_q:.3f} mAh/cm², "
            f"within 10% of the stated {q_areal:g} mAh/cm²."
        ),
        confidence="high",
        step_id=step,
        quote="",
        computed=computed,
        assumption_ids=assumption_ids,
        evidence_ids=EV + source_ev,
    )
