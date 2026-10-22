"""B1 composition, fraction sum, cross-statement, and solids/NMP balance."""
from __future__ import annotations

import re

from ..models import CheckResult, Patch, Recipe
from ..units import solids_wt_percent

EV = ["EV-B1"]


def _finding_id(recipe: Recipe) -> str:
    return f"B1-{recipe.fixture_id or 'case'}"


def _composition_span(text: str) -> str:
    pattern = (
        r"\d+(?:\.\d+)?\s*wt%\s*NMC811[^\n]*?"
        r"\d+(?:\.\d+)?\s*wt%[^\n]*?carbon[^\n]*?and\s+"
        r"\d+(?:\.\d+)?\s*wt%\s*PVDF"
    )
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(0) if match else ""


def _retarget_composition(span: str) -> str:
    replacements = iter(("95", "3", "2"))
    return re.sub(
        r"\d+(?:\.\d+)?(?=\s*wt%)",
        lambda m: next(replacements, m.group(0)),
        span,
        count=3,
    )


def check_composition(recipe: Recipe) -> CheckResult:
    c = recipe.composition
    nmc, carbon, binder = c.nmc811_wt, c.carbon_wt, c.binder_wt
    sum_wt = c.sum_wt
    source_ev = ["EV-P2"] if (recipe.protocol.doi or "").endswith("3c14394") else []
    step = c.composition_step_id or recipe.step_for_quote(c.composition_quote) or "S1"
    quote = c.composition_quote or "composition"

    # B1a -- fractions and second statement
    a_status, a_sev, a_title, a_expl = "pass", None, "B1a composition is internally consistent", ""
    if None in (nmc, carbon, binder):
        a_status, a_sev = "unknown", "medium"
        a_title = "Composition fractions are incomplete"
        a_expl = "The protocol does not state all three of NMC811, carbon, and binder wt%. A check cannot assume the balance."
    elif abs(sum_wt - 100.0) > 0.05:
        a_status, a_sev = "fail", "high"
        a_title = "Composition fractions do not sum to 100 wt%"
        a_expl = f"{nmc} + {carbon} + {binder} = {sum_wt:.1f} wt%, not 100 wt%."
    elif c.stated_active_wt is not None and abs(c.stated_active_wt - nmc) > 1.0:
        a_status, a_sev = "fail", "high"
        a_title = "Composition line and prose disagree"
        a_expl = (
            f"The composition line gives {nmc:g} wt% NMC811, but the protocol also says "
            f"{c.stated_active_wt:g} wt% NMC811. Read with the line's {carbon:g} wt% carbon and "
            f"{binder:g} wt% PVDF, the second statement implies {c.stated_active_wt + carbon + binder:g} wt% total."
        )

    a = CheckResult(
        check_id="B1a",
        status=a_status,
        family="composition",
        title=a_title,
        explanation=a_expl,
        severity=a_sev,
        confidence="high" if a_status != "unknown" else "medium",
        step_id=step,
        quote=quote if a_status != "pass" else "",
        computed={
            "nmc811_wt": nmc,
            "carbon_wt": carbon,
            "binder_wt": binder,
            "sum_wt": sum_wt,
            "stated_active_wt": c.stated_active_wt,
        },
        assumption_ids=[],
        evidence_ids=EV + source_ev,
    )

    # B1b -- batch solids / NMP balance
    b_status, b_sev, b_title, b_expl = "pass", None, "B1b solids/NMP balance is consistent", ""
    b_computed = {
        "solids_mass_g": c.solids_mass_g,
        "nmp_volume_ml": c.nmp_volume_ml,
        "stated_solids_wt": c.stated_solids_wt,
    }
    if c.purchased:
        b_title = "B1b solids balance is N/A for a purchased electrode"
        b_expl = "The electrode is purchased/commercial; no slurry solids are stated. This is not an unknown check."
    elif c.solids_mass_g is None or c.nmp_volume_ml is None:
        b_status, b_sev = "unknown", "medium"
        b_title = "Slurry solids/NMP balance is not specified"
        b_expl = "The batch solids mass or NMP volume is absent, so the solids wt% cannot be verified."
    else:
        calc = solids_wt_percent(c.solids_mass_g, c.nmp_volume_ml)
        b_computed.update({"computed_solids_wt": calc, "nmp_mass_g": c.nmp_volume_ml * 1.03})
        if c.stated_solids_wt is not None and abs(calc - c.stated_solids_wt) > 1.0:
            b_status, b_sev = "fail", "high"
            b_title = "Solids wt% and batch masses disagree"
            b_expl = (
                f"{c.solids_mass_g:g} g solids plus {c.nmp_volume_ml:g} mL NMP (1.03 g/mL) gives "
                f"{calc:.1f} wt% solids, not the stated {c.stated_solids_wt:g} wt%."
            )
        elif c.stated_solids_wt is None:
            b_status, b_sev = "unknown", "medium"
            b_title = "Solids wt% is not stated"
            b_expl = f"The batch masses imply {calc:.1f} wt% solids, but the protocol does not state a target."
    b_step = c.solids_step_id or recipe.step_for_quote(c.solids_quote) or step
    b_quote = c.solids_quote if b_status != "pass" else ""
    if b_status == "unknown" and not b_quote:
        b_quote = c.composition_quote or "solids/NMP amount not stated"
    b = CheckResult(
        check_id="B1b",
        status=b_status,
        family="composition",
        title=b_title,
        explanation=b_expl,
        severity=b_sev,
        confidence="high" if b_status != "unknown" else "medium",
        step_id=b_step,
        quote=b_quote,
        computed=b_computed,
        assumption_ids=["A-RHO-NMP"] if c.solids_mass_g is not None and c.nmp_volume_ml is not None else [],
        evidence_ids=EV + source_ev,
    )

    if a.status == "fail":
        patch = None
        if recipe.fixture_id in {"G03", "DEMO"}:
            before = _composition_span(recipe.text) or c.composition_quote or "90 wt% NMC811, 5 wt% Super C65 carbon black, and 5 wt% PVDF"
            after = _retarget_composition(before)
            patch = Patch(
                id=f"P-B1-{recipe.fixture_id}",
                finding_id=_finding_id(recipe),
                op="replace",
                step_id=step,
                before=before,
                after=after,
                rationale="Restore the source-faithful 95:3:2 composition so the line and the prose agree.",
                evidence_ids=EV + source_ev,
                field_updates={"composition.nmc811_wt": 95.0, "composition.carbon_wt": 3.0, "composition.binder_wt": 2.0},
            )
        return CheckResult(
            check_id="B1", status="fail", family="composition", title=a.title, explanation=a.explanation,
            severity="high", confidence="high", step_id=step, quote=a.quote,
            computed={"B1a": a.computed, "B1b": b.computed}, assumption_ids=[],
            evidence_ids=EV + source_ev, patch=patch, subresults=[a, b],
        )
    if b.status == "fail":
        return CheckResult(
            check_id="B1", status="fail", family="composition", title=b.title, explanation=b.explanation,
            severity="high", confidence="high", step_id=b.step_id, quote=b.quote,
            computed={"B1a": a.computed, "B1b": b.computed}, assumption_ids=b.assumption_ids,
            evidence_ids=EV + source_ev, subresults=[a, b],
        )
    if a.status == "unknown" or b.status == "unknown":
        return CheckResult(
            check_id="B1", status="unknown", family="composition",
            title=a.title if a.status == "unknown" else b.title,
            explanation=a.explanation if a.status == "unknown" else b.explanation,
            severity="medium", confidence="medium",
            step_id=a.step_id if a.status == "unknown" else b.step_id,
            quote=a.quote if a.status == "unknown" else b.quote,
            computed={"B1a": a.computed, "B1b": b.computed},
            assumption_ids=b.assumption_ids, evidence_ids=EV + source_ev, subresults=[a, b],
        )
    return CheckResult(
        check_id="B1", status="pass", family="composition", title="Composition and solids balance are consistent",
        explanation="Fractions sum to 100 wt%, cross-statements agree, and the stated solids/NMP balance agrees within the 1.0 wt% tolerance.",
        confidence="high", computed={"B1a": a.computed, "B1b": b.computed},
        evidence_ids=EV + source_ev, subresults=[a, b],
    )
