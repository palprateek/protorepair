"""Licensed public fixtures and the optional local-only evaluation fixtures.

Public fixtures are adapted P2 (Llanos et al., CC BY 4.0), P4 (Zhang et al.,
CC BY 4.0), and P5 (Yan et al., CC BY 4.0) text. P1/P3-derived fixtures live
under .scratch and are loaded only when PROTOREPAIR_LOCAL is available; they are
never part of the public export.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path

from .models import (
    Ambiguity,
    Anode,
    Atmosphere,
    Composition,
    DryingStage,
    Electrode,
    Electrolyte,
    Protocol,
    Recipe,
    Salt,
    Separator,
    default_assumptions,
)
from .preparse import preparse


P2_ATTRIBUTION = (
    "Adapted from Llanos et al., High Voltage Cycling Stability of LiF-Coated NMC811 Electrode, "
    "ACS Appl. Mater. Interfaces 2024, 16, 2216-2230, DOI 10.1021/acsami.3c14394, CC BY 4.0. "
    "Changes: commercial NMC811 substituted for the in-house material; text condensed; LiF coating omitted; "
    "H1-H4 are synthetic faults that alter composition, loading, electrolyte volume, and atmosphere; "
    "the underlying assembly procedure is retained."
)
G14_ATTRIBUTION = (
    P2_ATTRIBUTION
    + " G14 clean-control additions: 50 um Li stored in the glovebox; 20 g solids + 37.5 mL NMP with "
      "34.1 wt% solids; CAM powder drying at 120 C under vacuum for 3 h; and explicit water test values "
      "(NMC811 200, carbon 500, PVDF 2000, separator 75, electrolyte 15 ppm). These are test values, "
      "not claims about the published paper."
)
P4_ATTRIBUTION = (
    "Adapted from Zhang et al., Nat Commun 2025, 16, 3344, DOI 10.1038/s41467-025-58627-3, CC BY 4.0. "
    "Changes: text condensed; the paper's 5.0 wt% NMP and 3 mAh g-1 are retained as natural ambiguities; "
    "Li thickness is changed to 4 um only in G08."
)
P5_ATTRIBUTION = (
    "Adapted from Yan et al., Nat Commun 2026, 17, DOI 10.1038/s41467-026-72530-5, CC BY 4.0. "
    "Changes: text condensed; an NMC811 water value of 1,200 ppm is added only in G10; salt concentrations "
    "are reduced in G11; the Li-cell electrolyte volume is left unstated."
)

P2_BASE = """NMC811 || Li coin-cell assembly (adapted from Llanos et al., ACS AMI 2024, CC BY 4.0).
1. Mix 95 wt% NMC811, 3 wt% Super C65 carbon black, and 2 wt% PVDF in NMP. The cathode contains 95 wt% NMC811. [NMP amount and slurry solids are not stated in the source.]
2. Coat the slurry on 20 um Al foil to a total dry loading of 10.5 mg/cm², corresponding to ~2.0 mAh/cm² at 200 mAh/g. Punch 14 mm cathodes.
3. Dry the coated electrodes in a fume hood overnight, then at 80 °C for 4 h; calender; final dry at 80 °C under vacuum for at least 12 h before transfer to the glovebox.
4. Assemble CR2016 cells in an Ar glovebox with H2O and O2 <1 ppm, using a 19 mm Li foil anode (thickness not stated), a 19 mm Whatman GF/A separator, and 200 µL of 1.0 M LiPF6 in EC:DMC (1:1 v/v).
5. Rest the cells for 24 h before cycling.
"""

H1_TEXT = P2_BASE.replace(
    "Mix 95 wt% NMC811, 3 wt% Super C65 carbon black, and 2 wt% PVDF",
    "Mix 90 wt% NMC811, 5 wt% Super C65 carbon black, and 5 wt% PVDF",
)
H2_TEXT = P2_BASE.replace("10.5 mg/cm²", "21 mg/cm²")
H3_TEXT = P2_BASE.replace("200 µL", "20 µL")
H4_TEXT = P2_BASE.replace("an Ar glovebox", "an N2 glovebox")
DEMO_TEXT = (
    H1_TEXT.replace("200 µL", "20 µL")
    .replace("an Ar glovebox", "an N2 glovebox")
)

G14_TEXT = """NMC811 || Li coin-cell assembly (adapted from Llanos et al., ACS AMI 2024, CC BY 4.0; G14 clean control).
1. Mix 95 wt% NMC811, 3 wt% Super C65 carbon black, and 2 wt% PVDF in NMP. The cathode contains 95 wt% NMC811. Use 20 g total solids and 37.5 mL NMP, giving 34.1 wt% solids.
2. Coat the slurry on 20 um Al foil to a total dry loading of 10.5 mg/cm², corresponding to ~2.0 mAh/cm² at 200 mAh/g. Punch 14 mm cathodes.
3. Dry the CAM powder at 120 °C under vacuum for 3 h. Dry the coated electrodes in a fume hood overnight, then at 80 °C for 4 h; calender; final dry at 80 °C under vacuum for at least 12 h before transfer to the glovebox.
4. Assemble CR2016 cells in an Ar glovebox with H2O and O2 <1 ppm, using a 19 mm Li foil anode (50 µm, stored in the glovebox), a 19 mm Whatman GF/A separator (49.4 mg test mass), and 200 µL of 1.0 M LiPF6 in EC:DMC (1:1 v/v).
5. Water test values: NMC811 200 ppm, carbon 500 ppm, PVDF 2000 ppm, separator 75 ppm, electrolyte 15 ppm. Rest the cells for 24 h before cycling.
"""

P4_TEXT = """NMC811 || Li coin cell (adapted from Zhang et al., Nat Commun 2025, 16, 3344, CC BY 4.0).
1. Mix 90 wt% NMC811, 5 wt% Super P, and 5 wt% PVDF; the slurry contains 5.0 wt% NMP.
2. Coat on Al foil to an areal capacity of ~3 mAh/cm²; the electrode delivers 3 mAh g−1 at 0.1C. Punch 12 mm cathodes.
3. Dry the electrode at 100 °C under vacuum (time not stated).
4. Assemble in an Ar glovebox using 40 µm Li (Li excess ≈ 3), a 12 mm Celgard 2325 separator, and 70 µL of 1.0 M LiFSI in DEE:DME 9:1 + 0.1 M PQA-NO3.
5. No water values are stated.
"""
P4_LI_TEXT = P4_TEXT.replace("40 µm Li", "4 µm Li")

P5_TEXT = """NMC811 || Li coin cell (adapted from Yan et al., Nat Commun 2026, 17, CC BY 4.0).
1. Use a purchased 95:3:2 NMC811 electrode with a total dry loading of 5.26 mg/cm² and an areal capacity of 1.0 mAh/cm²; punch 14 mm cathodes.
2. Dry the purchased electrode at 120 °C under vacuum for 12 h.
3. Assemble in an Ar glovebox with H2O and O2 <0.1 ppm, using 150 µm Li, a 16 mm Celgard 2500 separator, and 0.8 M LiFSI + 0.2 M LiDFOB in EC:EMC 3:7.
4. The Li-cell electrolyte volume is not stated. No water values are stated.
"""
P5_WATER_TEXT = P5_TEXT.replace(
    "No water values are stated.",
    "NMC811 water content is 1,200 ppm by KFT.",
)
P5_MOLARITY_TEXT = P5_TEXT.replace(
    "0.8 M LiFSI + 0.2 M LiDFOB",
    "0.08 M LiFSI + 0.02 M LiDFOB called 1 M total",
)


def _steps(text: str):
    return preparse(text).steps


def _base_recipe(
    fixture_id: str,
    text: str,
    *,
    title: str,
    doi: str,
    source: str,
    license: str,
    attribution: str,
    cell_format: str | None = "CR2016",
    composition: Composition | None = None,
    electrode: Electrode | None = None,
    anode: Anode | None = None,
    separator: Separator | None = None,
    electrolyte: Electrolyte | None = None,
    atmosphere: Atmosphere | None = None,
    water_ppm: dict[str, float] | None = None,
    ambiguities: list[Ambiguity] | None = None,
    public: bool = True,
) -> Recipe:
    r = Recipe(
        protocol=Protocol(
            title=title,
            doi=doi,
            url=f"https://doi.org/{doi}" if doi else None,
            license=license,
            source=source,
            attribution=attribution,
            cell_format=cell_format,
            public=public,
        ),
        text=text,
        steps=_steps(text),
        composition=composition or Composition(),
        electrode=electrode or Electrode(),
        anode=anode or Anode(),
        separator=separator or Separator(),
        electrolyte=electrolyte or Electrolyte(),
        atmosphere=atmosphere or Atmosphere(),
        water_ppm=water_ppm or {},
        water_is_test=set(water_ppm or {}),
        assumptions=default_assumptions(),
        ambiguities=ambiguities or [],
        fixture_id=fixture_id,
    )
    return r


def _p2(fixture_id: str, text: str, *, comp=(95, 3, 2), stated=95, total=10.5, vol=200, gas="Ar") -> Recipe:
    if fixture_id == "G02":
        attribution = P2_ATTRIBUTION
    elif fixture_id == "G14":
        attribution = G14_ATTRIBUTION
    else:
        attribution = P2_ATTRIBUTION
    r = _base_recipe(
        fixture_id,
        text,
        title="NMC811 || Li coin-cell assembly (P2-derived)",
        doi="10.1021/acsami.3c14394",
        source="Llanos et al., ACS Appl. Mater. Interfaces 2024, 16, 2216-2230",
        license="CC BY 4.0",
        attribution=attribution,
        composition=Composition(
            nmc811_wt=comp[0],
            carbon_wt=comp[1],
            binder_wt=comp[2],
            stated_active_wt=stated,
            composition_quote=f"{comp[0]} wt% NMC811, {comp[1]} wt% Super C65 carbon black, and {comp[2]} wt% PVDF",
            cross_statement_quote="The cathode contains 95 wt% NMC811.",
        ),
        electrode=Electrode(
            total_loading_mg_cm2=total,
            active_loading_mg_cm2=None,
            areal_capacity_mAh_cm2=2.0,
            specific_capacity_mAh_g=200.0,
            active_fraction=stated / 100.0,
            diameter_mm=14.0,
            quote=f"total dry loading of {total:g} mg/cm², corresponding to ~2.0 mAh/cm²",
        ),
        anode=Anode(material="Li metal", thickness_um=50.0 if fixture_id == "G14" else None, diameter_mm=19.0,
                    quote="a 19 mm Li foil anode"),
        separator=Separator(material="Whatman GF/A", diameter_mm=19.0,
                            mass_mg=49.4 if fixture_id == "G14" else None,
                            mass_is_assumption=fixture_id != "G14",
                            water_ppm=75.0 if fixture_id == "G14" else None,
                            quote="a 19 mm Whatman GF/A separator"),
        electrolyte=Electrolyte(
            volume_uL=vol,
            volume_basis="total",
            salts=[Salt("LiPF6", 1.0)],
            total_molarity=1.0,
            solvents="EC:DMC (1:1 v/v)",
            water_ppm=15.0 if fixture_id == "G14" else None,
            quote="200 µL of 1.0 M LiPF6 in EC:DMC (1:1 v/v)",
        ),
        atmosphere=Atmosphere(gas=gas, glovebox=True, o2_ppm=1.0, h2o_ppm=1.0,
                             quote="an Ar glovebox with H2O and O2 <1 ppm"),
        water_ppm=(
            {"NMC811": 200.0, "carbon": 500.0, "PVDF": 2000.0, "separator": 75.0, "electrolyte": 15.0}
            if fixture_id == "G14" else {}
        ),
    )
    if fixture_id == "G14":
        r.composition.solids_mass_g = 20.0
        r.composition.nmp_volume_ml = 37.5
        r.composition.stated_solids_wt = 34.1
        r.electrode.drying = [
            DryingStage("CAM", 120.0, 3.0, True, quote="Dry the CAM powder at 120 °C under vacuum for 3 h."),
            DryingStage("electrode", 80.0, 12.0, True, quote="final dry at 80 °C under vacuum for at least 12 h"),
        ]
    else:
        r.electrode.drying = [
            DryingStage("electrode", 80.0, 12.0, True, quote="final dry at 80 °C under vacuum for at least 12 h"),
        ]
    for stage in r.electrode.drying:
        stage.step_id = r.step_for_quote(stage.quote)
    return r


def _p4(fixture_id: str, text: str) -> Recipe:
    amb = [
        Ambiguity(
            class_id="A1",
            field="composition.nmp_basis",
            issue="5.0 wt% NMP does not say whether the basis is slurry, solids, or solvent.",
            quote="the slurry contains 5.0 wt% NMP",
            title="NMP amount has no clear basis",
            explanation="The protocol says 5.0 wt% NMP without saying wt% of what. The value is retained as ambiguous, not converted to a volume.",
        ),
        Ambiguity(
            class_id="A2",
            field="electrode.areal_capacity",
            issue="3 mAh g−1 is a gravimetric unit where areal capacity is being discussed.",
            quote="the electrode delivers 3 mAh g−1 at 0.1C",
            title="Capacity unit/basis ambiguity",
            explanation="The text says 3 mAh g−1 while describing an areal capacity. Do not silently turn it into mAh/cm²; ask for the basis.",
        ),
    ]
    r = _base_recipe(
        fixture_id,
        text,
        title="NMC811 || Li coin cell (P4-derived)",
        doi="10.1038/s41467-025-58627-3",
        source="Zhang et al., Nat Commun 2025, 16, 3344",
        license="CC BY 4.0",
        attribution=P4_ATTRIBUTION,
        cell_format=None,
        composition=Composition(
            nmc811_wt=90.0,
            carbon_wt=5.0,
            binder_wt=5.0,
            stated_active_wt=90.0,
            composition_quote="90 wt% NMC811, 5 wt% Super P, and 5 wt% PVDF",
        ),
        electrode=Electrode(
            total_loading_mg_cm2=None,
            active_loading_mg_cm2=None,
            areal_capacity_mAh_cm2=3.0,
            specific_capacity_mAh_g=None,
            active_fraction=0.9,
            diameter_mm=12.0,
            drying=[DryingStage("electrode", 100.0, None, True, quote="Dry the electrode at 100 °C under vacuum (time not stated).")],
            quote="an areal capacity of ~3 mAh/cm²",
        ),
        anode=Anode(
            thickness_um=4.0 if fixture_id == "G08" else 40.0,
            diameter_mm=12.0,
            stated_ratio=3.0,
            intent="excess",
            quote="40 µm Li (Li excess ≈ 3)" if fixture_id != "G08" else "4 µm Li (Li excess ≈ 3)",
        ),
        separator=Separator(material="Celgard 2325", diameter_mm=12.0, quote="a 12 mm Celgard 2325 separator"),
        electrolyte=Electrolyte(
            volume_uL=70.0,
            volume_basis="total",
            salts=[Salt("LiFSI", 1.0), Salt("PQA-NO3", 0.1)],
            total_molarity=None,
            solvents="DEE:DME 9:1",
            quote="70 µL of 1.0 M LiFSI in DEE:DME 9:1 + 0.1 M PQA-NO3",
        ),
        atmosphere=Atmosphere(gas="Ar", glovebox=True, o2_ppm=None, h2o_ppm=None,
                             quote="Assemble in an Ar glovebox"),
        ambiguities=amb,
    )
    for a in r.ambiguities:
        a.step_id = r.step_for_quote(a.quote)
    for d in r.electrode.drying:
        d.step_id = r.step_for_quote(d.quote)
    return r


def _p5(fixture_id: str, text: str) -> Recipe:
    water = {"NMC811": 1200.0} if fixture_id == "G10" else {}
    salts = [Salt("LiFSI", 0.8), Salt("LiDFOB", 0.2)]
    total = 1.0
    if fixture_id == "G11":
        salts = [Salt("LiFSI", 0.08), Salt("LiDFOB", 0.02)]
        total = 1.0
    r = _base_recipe(
        fixture_id,
        text,
        title="NMC811 || Li coin cell (P5-derived)",
        doi="10.1038/s41467-026-72530-5",
        source="Yan et al., Nat Commun 2026, 17",
        license="CC BY 4.0",
        attribution=P5_ATTRIBUTION,
        cell_format=None,
        composition=Composition(
            nmc811_wt=95.0,
            carbon_wt=3.0,
            binder_wt=2.0,
            stated_active_wt=95.0,
            purchased=True,
            composition_quote="purchased 95:3:2 NMC811 electrode",
        ),
        electrode=Electrode(
            total_loading_mg_cm2=5.26,
            areal_capacity_mAh_cm2=1.0,
            specific_capacity_mAh_g=200.0,
            active_fraction=0.95,
            diameter_mm=14.0,
            drying=[DryingStage("electrode", 120.0, 12.0, True, quote="Dry the purchased electrode at 120 °C under vacuum for 12 h.")],
            quote="total dry loading of 5.26 mg/cm² and an areal capacity of 1.0 mAh/cm²",
        ),
        anode=Anode(thickness_um=150.0, diameter_mm=16.0, quote="150 µm Li"),
        separator=Separator(material="Celgard 2500", diameter_mm=16.0, quote="a 16 mm Celgard 2500 separator"),
        electrolyte=Electrolyte(
            volume_uL=None,
            volume_basis="not stated",
            salts=salts,
            total_molarity=total,
            solvents="EC:EMC 3:7",
            water_ppm=None,
            quote="0.8 M LiFSI + 0.2 M LiDFOB in EC:EMC 3:7" if fixture_id != "G11" else "0.08 M LiFSI + 0.02 M LiDFOB called 1 M total",
        ),
        atmosphere=Atmosphere(gas="Ar", glovebox=True, o2_ppm=0.1, h2o_ppm=0.1,
                             quote="an Ar glovebox with H2O and O2 <0.1 ppm"),
        water_ppm=water,
    )
    for d in r.electrode.drying:
        d.step_id = r.step_for_quote(d.quote)
    return r


def _public_fixtures() -> dict[str, Recipe]:
    fixtures: dict[str, Recipe] = {}
    fixtures["G02"] = _p2("G02", P2_BASE)
    fixtures["G03"] = _p2("G03", H1_TEXT, comp=(90, 5, 5))
    fixtures["G04"] = _p2("G04", H2_TEXT, total=21.0)
    fixtures["G05"] = _p2("G05", H3_TEXT, vol=20.0)
    fixtures["G06"] = _p2("G06", H4_TEXT, gas="N2")
    fixtures["G07"] = _p4("G07", P4_TEXT)
    fixtures["G08"] = _p4("G08", P4_LI_TEXT)
    fixtures["G09"] = _p5("G09", P5_TEXT)
    fixtures["G10"] = _p5("G10", P5_WATER_TEXT)
    fixtures["G11"] = _p5("G11", P5_MOLARITY_TEXT)
    fixtures["G14"] = _p2("G14", G14_TEXT)
    # aliases used by the demo UI
    for alias, base in (("H1", "G03"), ("H2", "G04"), ("H3", "G05"), ("H4", "G06")):
        fixtures[alias] = fixtures[base]
    fixtures["DEMO"] = _p2("DEMO", DEMO_TEXT, comp=(90, 5, 5), vol=20.0, gas="N2")
    return fixtures


_PUBLIC = _public_fixtures()


def _load_local() -> dict[str, Recipe]:
    """Load local-only P1/P3 fixtures if the private harness is present."""
    path = Path(__file__).resolve().parent.parent / ".scratch/protorepair/implementation/local_examples.py"
    if not path.exists():
        return {}
    spec = importlib.util.spec_from_file_location("protorepair_local_examples", path)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.local_fixtures()


def load_fixture(fixture_id: str) -> Recipe:
    if fixture_id in _PUBLIC:
        return _PUBLIC[fixture_id]
    local = _load_local()
    if fixture_id in local:
        return local[fixture_id]
    raise KeyError(f"unknown fixture {fixture_id!r}")


def fixture_ids(public_only: bool = True) -> list[str]:
    ids = [k for k in _PUBLIC if k not in {"H1", "H2", "H3", "H4", "DEMO"}]
    if public_only:
        return sorted(ids)
    local = _load_local()
    return sorted(set(ids) | set(local))


def public_examples() -> list[tuple[str, str]]:
    return [
        ("G14 clean control", "G14"),
        ("G02 P2 source base (unknowns visible)", "G02"),
        ("H1 composition/prose mismatch", "H1"),
        ("H2 loading/capacity mismatch", "H2"),
        ("H3 electrolyte underfill", "H3"),
        ("H4 N2 glovebox", "H4"),
        ("Demo composite H1+H3+H4", "DEMO"),
        ("P4 natural transfer case", "G07"),
        ("P5 base transfer case", "G09"),
    ]
