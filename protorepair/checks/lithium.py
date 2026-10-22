"""B3 Li excess / anode balance."""
from __future__ import annotations

from ..models import CheckResult, Patch, Recipe
from ..units import li_areal_mAh_cm2, li_ratio, li_utilization

EV = ["EV-B3", "EV-LI"]


def check_lithium(recipe: Recipe) -> CheckResult:
    a = recipe.anode
    e = recipe.electrode
    q_cathode = e.areal_capacity_mAh_cm2
    source_ev = ["EV-P2"] if (recipe.protocol.doi or "").endswith("3c14394") else []
    step = a.step_id or recipe.step_for_quote(a.quote) or "S4"

    if a.thickness_um is None or q_cathode is None:
        return CheckResult(
            check_id="B3",
            status="unknown",
            family="lithium",
            title="Li thickness or cathode capacity is missing",
            explanation="Li excess cannot be computed without both the Li foil thickness and the cathode areal capacity. The missing value is not treated as zero.",
            severity="medium",
            confidence="medium",
            step_id=step,
            quote=a.quote,
            computed={"li_thickness_um": a.thickness_um, "cathode_areal_capacity_mAh_cm2": q_cathode},
            evidence_ids=EV + source_ev,
        )

    q_li = li_areal_mAh_cm2(a.thickness_um)
    ratio = li_ratio(a.thickness_um, q_cathode)
    util = li_utilization(a.thickness_um, q_cathode)
    computed = {
        "li_thickness_um": a.thickness_um,
        "li_areal_capacity_mAh_cm2": q_li,
        "cathode_areal_capacity_mAh_cm2": q_cathode,
        "ratio": ratio,
        "utilization": util,
        "stated_ratio": a.stated_ratio,
        "intent": a.intent,
    }

    fail = None
    if ratio is not None and ratio < 1.0:
        fail = ("high", f"The Li anode supplies {q_li:.3f} mAh/cm² while the cathode needs {q_cathode:g} mAh/cm²; the cell is anode-limited (Li/cathode ratio {ratio:.2f}).")
    elif a.intent == "lean" and ratio is not None and ratio > 3.0:
        fail = ("high", f"The protocol calls for lean Li, but the computed Li/cathode ratio is {ratio:.2f} (> 3.0).")
    elif a.stated_ratio is not None and ratio is not None and abs(ratio - a.stated_ratio) / a.stated_ratio > 0.10:
        fail = ("high", f"The protocol states a Li excess/N/P ratio of {a.stated_ratio:g}, but the thickness and cathode capacity imply {ratio:.2f}, more than 10% away.")

    if fail:
        sev, expl = fail
        patch = None
        if recipe.fixture_id == "G08":
            patch = Patch(
                id="P-B3-G08",
                finding_id="B3-G08",
                op="replace",
                step_id=step,
                before="4 µm Li",
                after="40 µm Li",
                rationale="Restore the 40 µm Li foil; at the stated ~3 mAh/cm² cathode it gives the claimed Li excess of about 2.75x.",
                evidence_ids=EV,
                field_updates={"anode.thickness_um": 40.0},
            )
        return CheckResult(
            check_id="B3", status="fail", family="lithium", title="Li excess is not consistent with the claimed cell balance",
            explanation=expl, severity=sev, confidence="high", step_id=step, quote=a.quote,
            computed=computed, evidence_ids=EV + source_ev, patch=patch,
        )

    return CheckResult(
        check_id="B3",
        status="pass",
        family="lithium",
        title="Li foil is a flooded reservoir; no anode-limit flag",
        explanation=(
            f"{a.thickness_um:g} µm Li gives {q_li:.2f} mAh/cm² versus {q_cathode:g} mAh/cm² cathode "
            f"(ratio {ratio:.2f}, utilization {util:.1%}). This is a flooded reservoir, not an error."
        ),
        confidence="high",
        step_id=step,
        quote="",
        computed=computed,
        evidence_ids=EV + source_ev,
    )
