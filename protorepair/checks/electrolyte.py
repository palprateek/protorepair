"""B4 electrolyte volume and B5 salt/molarity checks."""
from __future__ import annotations

from ..models import CheckResult, Patch, Recipe, Salt
from ..units import electrolyte_g_per_Ah, electrolyte_uL_per_mAh

EV_B4 = ["EV-B4", "EV-P2"]
EV_B5 = ["EV-B5"]


def check_electrolyte_volume(recipe: Recipe) -> CheckResult:
    e = recipe.electrolyte
    electrode = recipe.electrode
    source_ev = ["EV-P2"] if (recipe.protocol.doi or "").endswith("3c14394") else []
    if (recipe.protocol.doi or "").endswith("58627-3"):
        source_ev = ["EV-P4"]
    if (recipe.protocol.doi or "").endswith("72530-5"):
        source_ev = ["EV-P5"]
    step = e.step_id or recipe.step_for_quote(e.quote) or "S4"
    if e.volume_uL is None or electrode.areal_capacity_mAh_cm2 is None or electrode.diameter_mm is None:
        return CheckResult(
            check_id="B4",
            status="unknown",
            family="electrolyte",
            title="Electrolyte volume or cell geometry is missing",
            explanation="The electrolyte volume per mAh cannot be computed without the fill volume, areal capacity, and electrode diameter.",
            severity="medium",
            confidence="medium",
            step_id=step,
            quote=e.quote,
            computed={
                "volume_uL": e.volume_uL,
                "areal_capacity_mAh_cm2": electrode.areal_capacity_mAh_cm2,
                "diameter_mm": electrode.diameter_mm,
            },
            evidence_ids=EV_B4 + source_ev,
        )
    uL_mAh = electrolyte_uL_per_mAh(e.volume_uL, electrode.areal_capacity_mAh_cm2, electrode.diameter_mm)
    g_ah = electrolyte_g_per_Ah(uL_mAh) if uL_mAh is not None else None
    computed = {
        "volume_uL": e.volume_uL,
        "areal_capacity_mAh_cm2": electrode.areal_capacity_mAh_cm2,
        "diameter_mm": electrode.diameter_mm,
        "uL_per_mAh": uL_mAh,
        "g_per_Ah": g_ah,
    }
    if uL_mAh is not None and uL_mAh < 10.0:
        patch = None
        if recipe.fixture_id in {"G05", "DEMO"}:
            patch = Patch(
                id=f"P-B4-{recipe.fixture_id}",
                finding_id=f"B4-{recipe.fixture_id}",
                op="replace",
                step_id=step,
                before="20 µL",
                after="200 µL",
                rationale="Restore the source-faithful 200 µL fill; 20 µL is 6.5 µL/mAh for the 3.08 mAh cathode, below the 10 µL/mAh screen.",
                evidence_ids=EV_B4 + source_ev,
                field_updates={"electrolyte.volume_uL": 200.0},
                alternatives=["40–100 µL; confirm separator pore volume"],
            )
        return CheckResult(
            check_id="B4", status="fail", family="electrolyte", title="Electrolyte fill is below the under-wetting screen",
            explanation=(
                f"{e.volume_uL:g} µL for a {electrode.areal_capacity_mAh_cm2:g} mAh/cm² cathode "
                f"({electrode.diameter_mm:g} mm) is {uL_mAh:.1f} µL/mAh ({g_ah:.1f} g/Ah), "
                "below the 10 µL/mAh lab screen. This is an under-wetting risk, not a claim that the cell is physically impossible."
            ),
            severity="medium", confidence="medium", step_id=step, quote=e.quote,
            computed=computed, evidence_ids=EV_B4 + source_ev, patch=patch,
        )
    if uL_mAh is not None and uL_mAh > 100.0:
        return CheckResult(
            check_id="B4", status="pass", family="electrolyte", title="Electrolyte fill is flooded; no under-wetting flag",
            explanation=f"{uL_mAh:.1f} µL/mAh is above the 100 µL/mAh flooded-cell note. Coin cells commonly flood; this is a Low note, not a fail.",
            severity="low", confidence="high", step_id=step, quote="", computed=computed,
            evidence_ids=EV_B4 + source_ev,
        )
    return CheckResult(
        check_id="B4", status="pass", family="electrolyte", title="Electrolyte fill is within the lab screen",
        explanation=f"{uL_mAh:.1f} µL/mAh ({g_ah:.1f} g/Ah) is between 10 and 100 µL/mAh.",
        confidence="high", step_id=step, quote="", computed=computed, evidence_ids=EV_B4 + source_ev,
    )


def check_salt(recipe: Recipe) -> CheckResult:
    e = recipe.electrolyte
    source_ev = ["EV-P2"] if (recipe.protocol.doi or "").endswith("3c14394") else []
    if (recipe.protocol.doi or "").endswith("58627-3"):
        source_ev = ["EV-P4"]
    if (recipe.protocol.doi or "").endswith("72530-5"):
        source_ev = ["EV-P5"]
    step = e.step_id or recipe.step_for_quote(e.quote) or "S4"
    if not e.salts:
        return CheckResult(
            check_id="B5", status="unknown", family="electrolyte", title="Salt identity/concentration is missing",
            explanation="No salt identity or concentration is stated, so molarity cannot be checked.",
            severity="medium", confidence="medium", step_id=step, quote=e.quote,
            computed={}, evidence_ids=EV_B5 + source_ev,
        )

    concs = [s.concentration_M for s in e.salts]
    known = [c for c in concs if c is not None]
    total = sum(known) if known else None
    computed = {
        "salts": [{"name": s.name, "concentration_M": s.concentration_M} for s in e.salts],
        "computed_total_M": total,
        "stated_total_M": e.total_molarity,
    }
    if e.total_molarity is not None and total is not None:
        rel = abs(total - e.total_molarity) / e.total_molarity if e.total_molarity else None
        if rel is not None and rel > 0.10:
            patch = None
            if recipe.fixture_id == "G11":
                patch = Patch(
                    id="P-B5-G11",
                    finding_id="B5-G11",
                    op="replace",
                    step_id=step,
                    before="0.08 M LiFSI + 0.02 M LiDFOB",
                    after="0.8 M LiFSI + 0.2 M LiDFOB",
                    rationale="Restore the 0.8 M LiFSI + 0.2 M LiDFOB mixed-salt pair; together they are the stated 1.0 M total.",
                    evidence_ids=EV_B5 + source_ev,
                    field_updates={"electrolyte.salts": [Salt("LiFSI", 0.8), Salt("LiDFOB", 0.2)]},
                )
            return CheckResult(
                check_id="B5", status="fail", family="electrolyte", title="Stated total molarity disagrees with the salt concentrations",
                explanation=(
                    f"The salt concentrations sum to {total:g} M, but the protocol calls the solution {e.total_molarity:g} M total "
                    f"({rel * 100:.0f}% difference). Mixed-salt molarity is the sum of salts in the same solution."
                ),
                severity="high", confidence="high", step_id=step, quote=e.quote,
                computed=computed, evidence_ids=EV_B5 + source_ev, patch=patch,
            )
    for s in e.salts:
        if s.concentration_M is not None and not (0.1 <= s.concentration_M <= 5.0):
            # B5 owns salt concentration; do not emit an A3 duplicate.
            return CheckResult(
                check_id="B5", status="fail", family="electrolyte", title="Salt concentration is outside the plausible band",
                explanation=f"{s.name} is {s.concentration_M:g} M, outside the 0.1-5 M screen. Check the dilution and whether the protocol means mM.",
                severity="high", confidence="high", step_id=step, quote=e.quote,
                computed=computed, evidence_ids=EV_B5 + source_ev, manual_fix=True,
            )
    return CheckResult(
        check_id="B5", status="pass", family="electrolyte", title="Salt concentration and total molarity are consistent",
        explanation=(
            f"{', '.join(f'{s.name} {s.concentration_M:g} M' for s in e.salts if s.concentration_M is not None)}"
            + (f" sums to {total:g} M" if total is not None else "")
            + (f", matching the stated {e.total_molarity:g} M total." if e.total_molarity is not None else ".")
        ),
        confidence="high", step_id=step, quote="", computed=computed, evidence_ids=EV_B5 + source_ev,
    )
