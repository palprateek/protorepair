"""Dataclasses for ProtoRepair's recipe, findings, patches, and results.

The model is deliberately plain: the LLM boundary only produces facts that are
validated into these objects; all arithmetic and decisions live in checks/.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, None: 4}
STATUS_ORDER = {"fail": 0, "unknown": 1, "pass": 2}


@dataclass
class Measurement:
    value: float | None = None
    min: float | None = None
    max: float | None = None
    unit: str | None = None
    qualifier: str = "exact"
    raw: str = ""

    @property
    def is_unknown(self) -> bool:
        return self.value is None and self.min is None and self.max is None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Protocol:
    title: str = ""
    doi: str | None = None
    url: str | None = None
    license: str | None = None
    source: str | None = None
    attribution: str | None = None
    cell_format: str | None = None
    public: bool = True


@dataclass
class Step:
    step_id: str
    text: str
    line_start: int = 0
    line_end: int = 0


@dataclass
class DryingStage:
    target: str  # "CAM", "electrode", "separator"
    temp_c: float | None = None
    time_h: float | None = None
    vacuum: bool | None = None
    pressure_bar: float | None = None
    quote: str = ""
    step_id: str | None = None


@dataclass
class Composition:
    nmc811_wt: float | None = None  # percent, not fraction
    carbon_wt: float | None = None
    binder_wt: float | None = None
    stated_active_wt: float | None = None
    stated_solids_wt: float | None = None
    solids_mass_g: float | None = None
    nmp_volume_ml: float | None = None
    nmp_mass_g: float | None = None
    purchased: bool = False
    composition_quote: str = ""
    composition_step_id: str | None = None
    solids_quote: str = ""
    solids_step_id: str | None = None
    cross_statement_quote: str | None = None

    @property
    def fractions(self) -> tuple[float | None, float | None, float | None]:
        return self.nmc811_wt, self.carbon_wt, self.binder_wt

    @property
    def sum_wt(self) -> float | None:
        vals = [v for v in self.fractions if v is not None]
        if len(vals) != 3:
            return None
        return float(sum(vals))

    @property
    def active_fraction(self) -> float | None:
        if self.stated_active_wt is not None:
            return self.stated_active_wt / 100.0
        if self.nmc811_wt is not None:
            return self.nmc811_wt / 100.0
        return None


@dataclass
class Electrode:
    material: str = "NMC811"
    total_loading_mg_cm2: float | None = None
    active_loading_mg_cm2: float | None = None
    areal_capacity_mAh_cm2: float | None = None
    specific_capacity_mAh_g: float | None = None
    active_fraction: float | None = None
    diameter_mm: float | None = None
    drying: list[DryingStage] = field(default_factory=list)
    quote: str = ""
    step_id: str | None = None


@dataclass
class Anode:
    material: str = "Li metal"
    thickness_um: float | None = None
    diameter_mm: float | None = None
    stated_ratio: float | None = None
    intent: str | None = None  # "lean", "excess", or None
    quote: str = ""
    step_id: str | None = None


@dataclass
class Salt:
    name: str
    concentration_M: float | None = None
    mass_g: float | None = None


@dataclass
class Electrolyte:
    volume_uL: float | None = None
    volume_basis: str | None = None
    salts: list[Salt] = field(default_factory=list)
    total_molarity: float | None = None
    solvents: str | None = None
    additives: str | None = None
    water_ppm: float | None = None
    density_mg_uL: float = 1.26
    quote: str = ""
    step_id: str | None = None


@dataclass
class Separator:
    material: str | None = None
    diameter_mm: float | None = None
    mass_mg: float | None = None
    mass_is_assumption: bool = False
    water_ppm: float | None = None
    quote: str = ""
    step_id: str | None = None


@dataclass
class Atmosphere:
    gas: str | None = None
    glovebox: bool | None = None
    o2_ppm: float | None = None
    h2o_ppm: float | None = None
    quote: str = ""
    step_id: str | None = None


@dataclass
class Ambiguity:
    class_id: str
    field: str
    issue: str
    quote: str
    step_id: str | None = None
    title: str = ""
    explanation: str = ""
    severity: str = "medium"
    status: str = "unknown"


@dataclass
class Assumption:
    id: str
    default: str
    use: str
    value: float | None = None
    editable: bool = True


@dataclass
class Recipe:
    protocol: Protocol = field(default_factory=Protocol)
    text: str = ""
    steps: list[Step] = field(default_factory=list)
    composition: Composition = field(default_factory=Composition)
    electrode: Electrode = field(default_factory=Electrode)
    anode: Anode = field(default_factory=Anode)
    separator: Separator = field(default_factory=Separator)
    electrolyte: Electrolyte = field(default_factory=Electrolyte)
    atmosphere: Atmosphere = field(default_factory=Atmosphere)
    water_ppm: dict[str, float] = field(default_factory=dict)
    water_is_test: set[str] = field(default_factory=set)
    assumptions: list[Assumption] = field(default_factory=list)
    ambiguities: list[Ambiguity] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    fixture_id: str | None = None

    @property
    def active_fraction(self) -> float | None:
        if self.electrode.active_fraction is not None:
            return self.electrode.active_fraction
        return self.composition.active_fraction

    def step_for_quote(self, quote: str | None) -> str | None:
        if not quote:
            return None
        for step in self.steps:
            if quote in step.text:
                return step.step_id
        return None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # sets are not JSON serializable
        data["water_is_test"] = sorted(self.water_is_test)
        return data


@dataclass
class Patch:
    id: str
    finding_id: str
    op: str
    step_id: str | None
    before: str
    after: str
    rationale: str
    evidence_ids: list[str] = field(default_factory=list)
    status: str = "proposed"
    manual_fix: bool = False
    field_updates: dict[str, Any] = field(default_factory=dict)
    alternatives: list[str] = field(default_factory=list)
    source_faithful: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "finding_id": self.finding_id,
            "op": self.op,
            "step_id": self.step_id,
            "before": self.before,
            "after": self.after,
            "rationale": self.rationale,
            "evidence_ids": list(self.evidence_ids),
            "status": self.status,
            "manual_fix": self.manual_fix,
            "alternatives": list(self.alternatives),
            "source_faithful": self.source_faithful,
        }


@dataclass
class Finding:
    id: str
    class_id: str
    family: str
    step_id: str | None
    quote: str
    title: str
    severity: str
    confidence: str
    status: str
    detection: str
    explanation: str
    assumption_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    patch_id: str | None = None
    computed: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "class_id": self.class_id,
            "family": self.family,
            "step_id": self.step_id,
            "quote": self.quote,
            "title": self.title,
            "severity": self.severity,
            "confidence": self.confidence,
            "status": self.status,
            "detection": self.detection,
            "explanation": self.explanation,
            "assumption_ids": list(self.assumption_ids),
            "evidence_ids": list(self.evidence_ids),
            "patch_id": self.patch_id,
            "computed": self.computed,
        }


@dataclass
class CheckResult:
    check_id: str
    status: str  # pass / fail / unknown
    family: str
    title: str
    explanation: str
    severity: str | None = None
    confidence: str = "high"
    step_id: str | None = None
    quote: str = ""
    computed: dict[str, Any] = field(default_factory=dict)
    assumption_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    patch: Patch | None = None
    manual_fix: bool = False
    subresults: list["CheckResult"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "family": self.family,
            "title": self.title,
            "explanation": self.explanation,
            "severity": self.severity,
            "confidence": self.confidence,
            "step_id": self.step_id,
            "quote": self.quote,
            "computed": self.computed,
            "assumption_ids": list(self.assumption_ids),
            "evidence_ids": list(self.evidence_ids),
            "patch": self.patch.to_dict() if self.patch else None,
            "manual_fix": self.manual_fix,
            "subresults": [s.to_dict() for s in self.subresults],
        }


@dataclass
class MoistureRow:
    source: str
    mass_mg: float | None
    ppm: float | None
    ug_h2o: float | None
    status: str
    basis: str
    assumption_id: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineResult:
    recipe: Recipe
    ledger: list[CheckResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    patches: list[Patch] = field(default_factory=list)
    readiness: str = "REVIEW"
    moisture: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, dict] = field(default_factory=dict)
    extraction_mode: str = "structured"
    warnings: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "readiness": self.readiness,
            "counts": self.counts,
            "extraction_mode": self.extraction_mode,
            "warnings": list(self.warnings),
            "recipe": self.recipe.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "patches": [p.to_dict() for p in self.patches],
            "checks": [c.to_dict() for c in self.ledger],
            "moisture": self.moisture,
            "evidence": self.evidence,
            "assumptions": [asdict(a) for a in self.recipe.assumptions],
            "missing_fields": list(self.recipe.missing_fields),
            "original_text": self.recipe.text,
        }


def default_assumptions() -> list[Assumption]:
    return [
        Assumption("A-QSPEC-200", "200 mAh/g", "NMC811 specific capacity when not stated", 200.0),
        Assumption("A-QSPEC-210", "210 mAh/g", "P3 specific capacity from 1C = 210 mA/g", 210.0),
        Assumption("A-RHO-NMP", "1.03 g/mL", "NMP mass from volume", 1.03),
        Assumption("A-RHO-EL", "1.26 mg/uL", "Electrolyte mass from volume", 1.26),
        Assumption("A-CAM-H2O", "500 ppm", "Sensitivity scenario only; not a measurement", 500.0),
        Assumption("A-CAM-H2O-200", "200 ppm", "Clean-control test value; not a published claim", 200.0),
        Assumption("A-CARBON-H2O", "500 ppm", "Sensitivity scenario only", 500.0),
        Assumption("A-PVDF-H2O", "2000 ppm", "Sensitivity scenario only", 2000.0),
        Assumption("A-SEP-H2O", "75 ppm", "Separator sensitivity scenario", 75.0),
        Assumption("A-EL-H2O", "15 ppm", "Electrolyte sensitivity scenario", 15.0),
        Assumption("A-SEP-MASS-P2", "49.4 mg", "19 mm GF/A scenario mass", 49.4),
        Assumption("A-SEP-MASS-P1", "5.39 mg", "19 mm Celgard 2320 scenario mass", 5.39),
    ]


def assumption_value(assumptions: list[Assumption], key: str, fallback: float | None = None) -> float | None:
    for a in assumptions:
        if a.id == key:
            return a.value if a.value is not None else fallback
    return fallback
