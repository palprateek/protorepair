"""C1 moisture budget and C2 atmosphere/drying checks."""
from __future__ import annotations

from ..models import CheckResult, DryingStage, MoistureRow, Patch, Recipe, assumption_value
from ..units import area_cm2, hf_ppm_equivalent, hf_upper_ug, ppm_on_basis, water_ug

EV_C1 = ["EV-C1", "EV-HF", "EV-430"]
EV_C2 = ["EV-C2", "EV-LI"]

LIMITS = {
    "NMC811": (500.0, "NMC811 post-dry/incoming"),
    "carbon": (None, "carbon black (no validated limit)"),
    "PVDF": (None, "PVDF (no validated limit)"),
    "separator": (75.0, "separator"),
    "electrolyte": (20.0, "electrolyte"),
}
DEFAULTS = {
    "NMC811": ("A-CAM-H2O", 500.0, "scenario default"),
    "carbon": ("A-CARBON-H2O", 500.0, "scenario default"),
    "PVDF": ("A-PVDF-H2O", 2000.0, "scenario default"),
    "separator": ("A-SEP-H2O", 75.0, "scenario default"),
    "electrolyte": ("A-EL-H2O", 15.0, "scenario default"),
}


def _mass_estimates(recipe: Recipe) -> dict[str, float | None]:
    e = recipe.electrode
    c = recipe.composition
    area = area_cm2(e.diameter_mm) if e.diameter_mm is not None else None
    fraction = recipe.active_fraction
    active_loading = e.active_loading_mg_cm2
    total = e.total_loading_mg_cm2
    if active_loading is None and total is not None and fraction:
        active_loading = total * fraction
    if total is None and active_loading is not None and fraction:
        total = active_loading / fraction
    out: dict[str, float | None] = {"NMC811": None, "carbon": None, "PVDF": None, "separator": None, "electrolyte": None}
    if active_loading is not None and area is not None:
        out["NMC811"] = active_loading * area
    if total is not None and area is not None:
        if c.carbon_wt is not None:
            out["carbon"] = total * c.carbon_wt / 100.0 * area
        if c.binder_wt is not None:
            out["PVDF"] = total * c.binder_wt / 100.0 * area
    if recipe.separator.mass_mg is not None:
        out["separator"] = recipe.separator.mass_mg
    elif recipe.separator.material:
        # Labeled sensitivity mass, never a measured value.
        out["separator"] = 49.4 if "GF/A" in recipe.separator.material else 5.39
    if recipe.electrolyte.volume_uL is not None:
        out["electrolyte"] = recipe.electrolyte.volume_uL * recipe.electrolyte.density_mg_uL
    return out


def _row(recipe: Recipe, key: str, mass: float | None, ppm: float | None, measured: bool) -> MoistureRow:
    limit, label = LIMITS[key]
    status = "unknown"
    note = ""
    if ppm is None:
        assumption, default_ppm, note_text = DEFAULTS[key]
        ppm_for_display = default_ppm
        status = "scenario"
        note = f"{note_text}; {assumption}"
        assumption_id = assumption
        evidence_ids = ["EV-C1"]
    else:
        ppm_for_display = ppm
        assumption_id = None
        evidence_ids = ["EV-C1"]
        if limit is not None and ppm > limit:
            status = "over-limit"
            note = f"above {limit:g} ppm limit"
        else:
            status = "within"
            note = f"limit {limit:g} ppm" if limit is not None else "no validated limit"
    ug = water_ug(mass, ppm_for_display) if mass is not None and ppm_for_display is not None else None
    return MoistureRow(
        source=label,
        mass_mg=mass,
        ppm=ppm_for_display,
        ug_h2o=ug,
        status=status,
        basis="per cell" if mass is not None else "mass missing",
        assumption_id=assumption_id,
        evidence_ids=evidence_ids,
        note=note,
    )


def check_moisture(recipe: Recipe) -> CheckResult:
    masses = _mass_estimates(recipe)
    measured = recipe.water_ppm
    rows: list[MoistureRow] = []
    for key in ["NMC811", "carbon", "PVDF", "separator", "electrolyte"]:
        rows.append(_row(recipe, key, masses.get(key), measured.get(key), key in measured))
    total = sum(r.ug_h2o for r in rows if r.ug_h2o is not None)
    nmc_mass = masses.get("NMC811")
    ppm_cam = ppm_on_basis(total, nmc_mass) if nmc_mass else None
    hf_ug = hf_upper_ug(total)
    el_mass = masses.get("electrolyte")
    ppm_hf = hf_ppm_equivalent(hf_ug, el_mass) if el_mass else None
    over = [r for r in rows if r.status == "over-limit"]
    missing = [r for r in rows if r.status == "scenario"]
    computed = {
        "rows": [r.to_dict() for r in rows],
        "total_ug_h2o": total,
        "measured_total_ug_h2o": sum(r.ug_h2o for r in rows if r.ug_h2o is not None and r.status != "scenario"),
        "ppm_on_CAM_basis": ppm_cam,
        "hf_upper_ug": hf_ug,
        "hf_ppm_equivalent_upper_bound": ppm_hf,
        "reference_430_ppm": {"value": 430, "basis": "Gr/NMC622", "note": "warning line only; not an NMC811 constant"},
        "limits": {k: v[0] for k, v in LIMITS.items()},
    }
    step = recipe.step_for_quote("No water values are stated.") or recipe.step_for_quote("NMC811 water content") or "S4"
    quote = "No water values are stated." if "No water values are stated." in recipe.text else ""
    if over:
        first = over[0]
        patch = None
        if recipe.fixture_id == "G10":
            patch = Patch(
                id="P-C1-G10",
                finding_id="C1-G10",
                op="replace",
                step_id=step,
                before="1,200 ppm",
                after="≤500 ppm (verify by KFT)",
                rationale="Bring the specified NMC811 water content back inside the ≤500 ppm incoming/post-dry screen; do not invent a measured value.",
                evidence_ids=EV_C1,
                field_updates={"water_ppm.NMC811": 500.0},
            )
        cam_text = f"≈{ppm_cam:.0f} ppm on CAM basis" if ppm_cam is not None else "CAM basis unavailable"
        hf_text = f"≈{ppm_hf:.0f} ppm-eq" if ppm_hf is not None else "electrolyte mass unavailable"
        return CheckResult(
            check_id="C1", status="fail", family="moisture", title="Specified water content exceeds a component limit",
            explanation=(
                f"{first.source} is {first.ppm:g} ppm, above its limit. The displayed total is "
                f"{total:.1f} µg H2O per cell ({cam_text}); HF upper bound {hf_text}. "
                "The 430 ppm line is a Gr/NMC622 warning, not an NMC811 constant."
            ),
            severity="high", confidence="high", step_id=step, quote=quote,
            computed=computed, evidence_ids=EV_C1, patch=patch,
        )
    if missing:
        return CheckResult(
            check_id="C1", status="unknown", family="moisture", title="Water values are missing; budget is a labeled sensitivity scenario",
            explanation=(
                "At least one major water source is not specified. The table uses labeled defaults only for sensitivity; "
                "the finding remains unknown, not a pass. Specify KFT values for NMC811, separator, and electrolyte at minimum."
            ),
            severity="medium", confidence="medium", step_id=step, quote=quote,
            computed=computed, evidence_ids=EV_C1,
        )
    cam_text = f"≈{ppm_cam:.0f} ppm CAM basis" if ppm_cam is not None else "CAM basis unavailable"
    hf_text = f"≈{ppm_hf:.0f} ppm-eq" if ppm_hf is not None else "electrolyte mass unavailable"
    return CheckResult(
        check_id="C1", status="pass", family="moisture", title="Specified water values are within component limits",
        explanation=(
            f"All major sources are specified and within their component limits. Total ≈{total:.1f} µg H2O per cell "
            f"({cam_text}; HF upper bound {hf_text}). The 430 ppm line is a Gr/NMC622 warning only."
        ),
        confidence="high", step_id=step, quote="", computed=computed, evidence_ids=EV_C1,
    )


def _drying_status(stage: DryingStage | None, target: str, purchased: bool = False) -> tuple[str, str, str]:
    if target == "CAM" and purchased:
        return "pass", "N/A", "Purchased electrode; no CAM powder drying step to check."
    if stage is None:
        return "unknown", "unknown", f"{target} drying is not stated."
    if stage.temp_c is None or stage.time_h is None or stage.vacuum is None:
        return "unknown", "unknown", f"{target} drying has an incomplete temperature/time/vacuum condition."
    if target == "CAM":
        if stage.temp_c < 100.0 or stage.time_h < 2.0:
            return "fail", "high", f"CAM powder is dried at {stage.temp_c:g} °C for {stage.time_h:g} h; the screen is 110-130 °C, vacuum, ≥3 h. Low-temperature CAM drying leaves residual water."
        if stage.temp_c < 110.0 or not stage.vacuum or stage.time_h < 3.0:
            return "unknown", "medium", f"CAM drying at {stage.temp_c:g} °C for {stage.time_h:g} h is close to but not inside the 110-130 °C, vacuum, ≥3 h screen."
        return "pass", "pass", f"CAM powder dried at {stage.temp_c:g} °C, vacuum, {stage.time_h:g} h."
    if stage.temp_c < 70.0 or not stage.vacuum or stage.time_h < 4.0:
        return "fail", "high", f"Coated electrode drying at {stage.temp_c:g} °C, vacuum={stage.vacuum}, {stage.time_h:g} h does not meet the 80 °C/vacuum/≥4 h NMP-removal screen."
    return "pass", "pass", f"Coated electrode dried at {stage.temp_c:g} °C, vacuum, {stage.time_h:g} h."


def check_atmosphere_drying(recipe: Recipe) -> CheckResult:
    a = recipe.atmosphere
    stages = {d.target: d for d in recipe.electrode.drying}
    cam = stages.get("CAM")
    elec = stages.get("electrode")
    purchased = recipe.composition.purchased
    atm_status, atm_sev, atm_expl = "pass", None, ""
    patch = None
    step = a.step_id or recipe.step_for_quote(a.quote) or "S4"

    gas = (a.gas or "").strip().lower()
    if gas == "n2" or "n2" in gas or "nitrogen" in gas:
        atm_status, atm_sev = "fail", "critical"
        atm_expl = "The protocol specifies an N2 glovebox. N2 is not recommended for Li metal; use Ar at <1 ppm H2O/O2."
        if recipe.fixture_id in {"G06", "DEMO"}:
            patch = Patch(
                id=f"P-C2-{recipe.fixture_id}",
                finding_id=f"C2-{recipe.fixture_id}",
                op="replace",
                step_id=step,
                before="an N2 glovebox",
                after="an Ar glovebox",
                rationale="Replace N2 with Ar; the source-faithful Li-metal atmosphere is Ar at <1 ppm H2O/O2.",
                evidence_ids=EV_C2,
                field_updates={"atmosphere.gas": "Ar"},
            )
    elif gas in {"air", "none", ""} or a.glovebox is False:
        atm_status, atm_sev = "fail", "critical"
        atm_expl = "Li metal is handled without an inert glovebox. This is a critical atmosphere/safety failure."
    elif gas == "ar" and a.h2o_ppm is not None and a.h2o_ppm <= 1.0 and (a.o2_ppm is None or a.o2_ppm <= 1.0):
        atm_status, atm_expl = "pass", f"Ar glovebox with H2O/O2 ≤1 ppm ({a.h2o_ppm:g}/{a.o2_ppm if a.o2_ppm is not None else '—'} ppm)."
    elif gas == "ar":
        atm_status, atm_sev = "unknown", "medium"
        atm_expl = "Ar is specified, but the H2O/O2 ppm is missing; the atmosphere condition is not verifiable."
    else:
        atm_status, atm_sev = "unknown", "medium"
        atm_expl = "The assembly atmosphere is not specified."

    cam_status, cam_sev, cam_expl = _drying_status(cam, "CAM", purchased)
    elec_status, elec_sev, elec_expl = _drying_status(elec, "electrode", purchased)

    sub = [
        CheckResult("C2-atmosphere", atm_status, "moisture", "Atmosphere", atm_expl, atm_sev, "high" if atm_status != "unknown" else "medium", step, a.quote, evidence_ids=EV_C2),
        CheckResult("C2-CAM", cam_status, "moisture", "CAM drying", cam_expl, cam_sev, "high" if cam_status != "unknown" else "medium", cam.step_id if cam else (recipe.step_for_quote("CAM powder") or step), cam.quote if cam else "", evidence_ids=EV_C2),
        CheckResult("C2-electrode", elec_status, "moisture", "Electrode drying", elec_expl, elec_sev, "high" if elec_status != "unknown" else "medium", elec.step_id if elec else (recipe.step_for_quote("Dry the coated electrode") or step), elec.quote if elec else "", evidence_ids=EV_C2),
    ]

    fail = [s for s in sub if s.status == "fail"]
    unknown = [s for s in sub if s.status == "unknown"]
    if fail:
        first = sorted(fail, key=lambda s: {"critical": 0, "high": 1, "medium": 2}.get(s.severity or "", 3))[0]
        if first.check_id == "C2-atmosphere" and patch is not None:
            patch = patch
        elif first.check_id != "C2-atmosphere":
            patch = None
            if recipe.fixture_id in {"G01", "G12"}:
                if recipe.fixture_id == "G01":
                    before, after = "pre-dry the NMC811 powder at ~60 °C under vacuum for 3 h", "pre-dry the NMC811 powder at 120 °C under vacuum for 3 h"
                    updates = {"drying.CAM.temp_c": 120.0}
                else:
                    before, after = "Dry the coated electrode at 60 °C under vacuum for 10 h", "Dry the coated electrode at 120 °C under vacuum for 10 h"
                    updates = {"drying.all.temp_c": 120.0}
                patch = Patch(
                    id=f"P-C2-{recipe.fixture_id}", finding_id=f"C2-{recipe.fixture_id}", op="replace",
                    step_id=first.step_id, before=before, after=after,
                    rationale="Raise the drying temperature to the 110-130 °C CAM/electrode screen; keep vacuum and duration.",
                    evidence_ids=EV_C2, field_updates=updates,
                )
        return CheckResult(
            check_id="C2", status="fail", family="moisture", title=first.title, explanation=first.explanation,
            severity=first.severity, confidence="high", step_id=first.step_id, quote=first.quote,
            computed={"atmosphere": atm_status, "cam": cam_status, "electrode": elec_status},
            evidence_ids=EV_C2, patch=patch, subresults=sub,
        )
    if unknown:
        first = unknown[0]
        return CheckResult(
            check_id="C2", status="unknown", family="moisture", title="Atmosphere/drying condition is incomplete",
            explanation=first.explanation + " This is an unknown, not a pass.",
            severity="medium", confidence="medium", step_id=first.step_id or step, quote=first.quote or a.quote,
            computed={"atmosphere": atm_status, "cam": cam_status, "electrode": elec_status},
            evidence_ids=EV_C2, subresults=sub,
        )
    return CheckResult(
        check_id="C2", status="pass", family="moisture", title="Atmosphere and drying conditions pass the screen",
        explanation="Ar glovebox within the ppm screen; CAM and coated-electrode drying meet the time/temperature/vacuum conditions.",
        confidence="high", computed={"atmosphere": atm_status, "cam": cam_status, "electrode": elec_status},
        evidence_ids=EV_C2, subresults=sub,
    )
