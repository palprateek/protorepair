"""Canonical units and deterministic conversions.

Pint is used for general conversions; the small formulas below are kept explicit
so the check layer never depends on LLM arithmetic.
"""
from __future__ import annotations

import math

import pint

_ureg = pint.UnitRegistry()
ureg = _ureg

UNIT_ALIASES = {
    "uL": "microliter",
    "µL": "microliter",
    "μL": "microliter",
    "ul": "microliter",
    "um": "micrometer",
    "µm": "micrometer",
    "μm": "micrometer",
    "mg/cm2": "milligram / centimeter ** 2",
    "mg/cm²": "milligram / centimeter ** 2",
    "mAh/cm2": "milliampere_hour / centimeter ** 2",
    "mAh/cm²": "milliampere_hour / centimeter ** 2",
    "mAh/g": "milliampere_hour / gram",
    "ml": "milliliter",
    "mL": "milliliter",
    "ppm": "dimensionless",
    "M": "mole / liter",
    "mol/L": "mole / liter",
}

MAGNITUDE_BANDS = {
    "total_loading_mg_cm2": (0.5, 50.0),
    "areal_capacity_mAh_cm2": (0.05, 10.0),
    "electrolyte_volume_uL": (5.0, 1000.0),
    "li_thickness_um": (10.0, 1000.0),
    "temperature_c": (-80.0, 200.0),
    "time_h": (0.1, 168.0),
    "pressure_bar": (0.001, 2.0),
    "salt_concentration_M": (0.1, 5.0),
}


def area_cm2(diameter_mm: float) -> float:
    return math.pi * (diameter_mm / 10.0) ** 2 / 4.0


def q_areal_mAh_cm2(active_loading_mg_cm2: float, qspec_mAh_g: float) -> float:
    return active_loading_mg_cm2 * qspec_mAh_g / 1000.0


def active_loading(total_loading: float, active_fraction: float) -> float:
    return total_loading * active_fraction


def qspec_inferred(q_areal: float, active_loading_mg_cm2: float) -> float | None:
    if active_loading_mg_cm2 <= 0:
        return None
    return 1000.0 * q_areal / active_loading_mg_cm2


def electrolyte_uL_per_mAh(volume_uL: float, q_areal: float, diameter_mm: float) -> float | None:
    q_cell = q_areal * area_cm2(diameter_mm)
    if q_cell <= 0:
        return None
    return volume_uL / q_cell


def electrolyte_g_per_Ah(uL_per_mAh: float) -> float:
    return uL_per_mAh * 1.26


def li_areal_mAh_cm2(thickness_um: float) -> float:
    return 0.2061 * thickness_um


def li_ratio(thickness_um: float, q_cathode_mAh_cm2: float) -> float | None:
    if q_cathode_mAh_cm2 <= 0:
        return None
    return li_areal_mAh_cm2(thickness_um) / q_cathode_mAh_cm2


def li_utilization(thickness_um: float, q_cathode_mAh_cm2: float) -> float | None:
    ratio = li_ratio(thickness_um, q_cathode_mAh_cm2)
    return None if ratio is None or ratio == 0 else 1.0 / ratio


def solids_wt_percent(solids_mass_g: float, nmp_volume_ml: float, nmp_density_g_ml: float = 1.03) -> float:
    nmp_mass = nmp_volume_ml * nmp_density_g_ml
    return 100.0 * solids_mass_g / (solids_mass_g + nmp_mass)


def nmp_mass_g(nmp_volume_ml: float, density_g_ml: float = 1.03) -> float:
    return nmp_volume_ml * density_g_ml


def water_ug(mass_mg: float, ppm: float) -> float:
    return mass_mg * ppm / 1000.0  # mg * ppm / 1e6 * 1e3 ug/mg


def hf_upper_ug(total_water_ug: float, ratio: float = 2.22) -> float:
    return ratio * total_water_ug


def hf_ppm_equivalent(hf_ug: float, electrolyte_mass_mg: float) -> float | None:
    if electrolyte_mass_mg <= 0:
        return None
    return hf_ug / electrolyte_mass_mg * 1000.0


def ppm_on_basis(mass_ug: float, basis_mass_mg: float) -> float | None:
    if basis_mass_mg <= 0:
        return None
    return mass_ug / basis_mass_mg * 1000.0


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a value exactly through Pint, rejecting unknown units."""
    src = UNIT_ALIASES.get(from_unit, from_unit)
    dst = UNIT_ALIASES.get(to_unit, to_unit)
    try:
        return (value * _ureg(src)).to(dst).magnitude
    except (pint.errors.UndefinedUnitError, pint.errors.DimensionalityError) as exc:
        raise ValueError(f"cannot convert {from_unit!r} to {to_unit!r}") from exc


def in_band(name: str, value: float | None) -> bool | None:
    if value is None or name not in MAGNITUDE_BANDS:
        return None
    lo, hi = MAGNITUDE_BANDS[name]
    return lo <= value <= hi


def fmt(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "unknown"
    if abs(value) >= 100:
        return f"{value:.{max(0, digits - 1)}f}"
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")
