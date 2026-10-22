"""Pipeline orchestration, readiness, and patch validation."""
from __future__ import annotations

import copy
from dataclasses import replace

from .checks.capacity import check_capacity
from .checks.composition import check_composition
from .checks.electrolyte import check_electrolyte_volume, check_salt
from .checks.lithium import check_lithium
from .checks.moisture import check_atmosphere_drying, check_moisture
from .checks.semantic import ambiguity_findings, check_semantic
from .checks.units_mag import check_units
from .evidence import load_evidence, resolve
from .fixtures import load_fixture
from .models import Finding, Patch, PipelineResult, Recipe
from .patches import PatchError, apply_patch, patch_guardrails


def derive_missing_fields(recipe: Recipe) -> list[str]:
    missing: list[str] = []
    c, e, a, el, sep = recipe.composition, recipe.electrode, recipe.anode, recipe.electrolyte, recipe.separator
    if not c.purchased and (c.solids_mass_g is None or c.nmp_volume_ml is None):
        missing.append("B1b solids/NMP balance")
    if a.thickness_um is None:
        missing.append("B3 Li thickness")
    if el.volume_uL is None:
        missing.append("B4 electrolyte volume")
    if not recipe.water_ppm:
        missing.append("C1 water values")
    if not c.purchased and not any(d.target == "CAM" for d in e.drying):
        missing.append("C2 CAM powder drying")
    if not recipe.atmosphere.gas or recipe.atmosphere.h2o_ppm is None:
        missing.append("C2 atmosphere ppm/gas")
    if e.diameter_mm is None:
        missing.append("B4 electrode diameter")
    return missing


def _finding(result, idx: int) -> Finding:
    severity = result.severity if result.severity in {"critical", "high", "medium", "low"} else "medium"
    if result.status == "unknown" and severity in {"critical", "high"}:
        severity = "medium"
    return Finding(
        id=f"{result.check_id}-{idx:03d}",
        class_id=result.check_id.split("-")[0],
        family=result.family,
        step_id=result.step_id,
        quote=result.quote,
        title=result.title,
        severity=severity,
        confidence=result.confidence,
        status=result.status,
        detection="D",
        explanation=result.explanation,
        assumption_ids=list(result.assumption_ids),
        evidence_ids=list(result.evidence_ids),
        patch_id=None,
        computed=result.computed,
    )


def readiness(findings: list[Finding]) -> str:
    if any(f.status == "fail" and f.severity in {"critical", "high"} for f in findings):
        return "NOT READY"
    if any(f.status == "fail" and f.severity == "medium" for f in findings):
        return "REVIEW"
    if any(f.status == "unknown" and f.severity in {"critical", "high", "medium"} for f in findings):
        return "REVIEW"
    return "READY"


def _run_checks(recipe: Recipe) -> tuple[list, list[Finding], list[Patch], list[str]]:
    ledger = []
    ledger.extend(check_units(recipe))
    b1 = check_composition(recipe)
    b2 = check_capacity(recipe)
    b3 = check_lithium(recipe)
    b4 = check_electrolyte_volume(recipe)
    b5 = check_salt(recipe)
    c1 = check_moisture(recipe)
    c2 = check_atmosphere_drying(recipe)
    ledger.extend([b1, b2, b3, b4, b5, c1, c2])
    ledger.extend(check_semantic(recipe))

    findings: list[Finding] = []
    patches: list[Patch] = []
    warnings: list[str] = []
    ambiguity = ambiguity_findings(recipe)
    findings.extend(ambiguity)
    has_ambiguity = bool(ambiguity)
    for result in [b1, b2, b3, b4, b5, c1, c2]:
        if result.status not in {"fail", "unknown"}:
            continue
        # The A1 ledger row is a summary; individual ambiguity findings carry the detail.
        if result.check_id == "A1" and has_ambiguity:
            continue
        f = _finding(result, len(findings) + 1)
        findings.append(f)
        if result.patch:
            p = result.patch
            p.finding_id = f.id
            f.patch_id = p.id
            findings[-1] = f
            patches.append(p)
            guard = patch_guardrails(p)
            if guard:
                warnings.extend(guard)
        if result.manual_fix:
            warnings.append(f"{f.id}: manual fix required; no automatic patch")
    # Sort by severity and class for a deterministic UI/export.
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: (order.get(f.severity, 4), f.class_id, f.id))
    return ledger, findings, patches, warnings


def run_pipeline(
    *,
    text: str | None = None,
    fixture_id: str | None = None,
    recipe: Recipe | None = None,
    evidence_mode: str | None = None,
    extraction_mode: str = "structured",
) -> PipelineResult:
    if recipe is None:
        if fixture_id is not None:
            recipe = load_fixture(fixture_id)
        elif text is not None:
            from .parser import parse_text

            recipe = parse_text(text)
            if extraction_mode == "structured":
                extraction_mode = "deterministic"
        else:
            raise ValueError("provide text, fixture_id, or recipe")
    recipe = copy.deepcopy(recipe)
    recipe.missing_fields = derive_missing_fields(recipe)
    ledger, findings, patches, warnings = _run_checks(recipe)
    snapshot = load_evidence(evidence_mode)
    used_ids: list[str] = []
    for f in findings:
        used_ids.extend(f.evidence_ids)
    for c in ledger:
        used_ids.extend(c.evidence_ids)
    evidence = {k: v for k, v in snapshot.items() if k in set(used_ids)}
    return PipelineResult(
        recipe=recipe,
        ledger=ledger,
        findings=findings,
        patches=patches,
        readiness=readiness(findings),
        moisture=next((c.computed for c in ledger if c.check_id == "C1"), {}),
        evidence=evidence,
        extraction_mode=extraction_mode,
        warnings=warnings,
    )


def validate_patch(result: PipelineResult, patch: Patch) -> dict:
    """Apply one patch to the original text/recipe and re-run all checks."""
    target_findings = [f for f in result.findings if f.id == patch.finding_id]
    target_classes = {f.class_id for f in target_findings}
    try:
        text, patched = apply_patch(result.recipe, patch)
    except (PatchError, KeyError, ValueError) as exc:
        return {"applied": False, "target_removed": False, "new_fail_classes": [], "error": str(exc)}
    after = run_pipeline(recipe=patched, evidence_mode="none")
    target_removed = not any(f.class_id in target_classes and f.status == "fail" for f in after.findings)
    before_fail_classes = {f.class_id for f in result.findings if f.status == "fail"}
    new_fail = [f.class_id for f in after.findings if f.status == "fail" and f.class_id not in before_fail_classes]
    return {
        "applied": True,
        "target_removed": target_removed,
        "new_fail_classes": sorted(set(new_fail)),
        "regressions": sorted(set(new_fail)),
        "text": text,
    }
