"""Apply and validate local patches; never merge a corrected protocol."""
from __future__ import annotations

import copy
from dataclasses import replace

from .models import DryingStage, Patch, Recipe, Salt


class PatchError(ValueError):
    pass


def apply_text_patch(text: str, patch: Patch) -> str:
    if patch.op != "replace":
        raise PatchError(f"unsupported patch op {patch.op!r}")
    if not patch.before:
        raise PatchError("patch has no before span")
    count = text.count(patch.before)
    if count == 0:
        raise PatchError(f"patch span not found: {patch.before!r}")
    # Replace exactly one contiguous occurrence; a repeated span is ambiguous.
    return text.replace(patch.before, patch.after, 1)


def _set_path(recipe: Recipe, path: str, value) -> None:
    if path == "drying.all.temp_c":
        for stage in recipe.electrode.drying:
            stage.temp_c = value
        return
    if path.startswith("drying."):
        _, target, field = path.split(".", 2)
        for stage in recipe.electrode.drying:
            if stage.target.lower() == target.lower():
                setattr(stage, field, value)
                return
        raise PatchError(f"drying target not found: {target}")
    if path.startswith("water_ppm."):
        _, key = path.split(".", 1)
        recipe.water_ppm[key] = value
        return
    parts = path.split(".")
    obj = recipe
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)


def apply_recipe_patch(recipe: Recipe, patch: Patch) -> Recipe:
    if patch.manual_fix:
        raise PatchError("manual fix is not an automatic patch")
    new = copy.deepcopy(recipe)
    for path, value in patch.field_updates.items():
        _set_path(new, path, copy.deepcopy(value))
    # Keep the source line in sync with the structured update where possible.
    return new


def apply_patch(recipe: Recipe, patch: Patch) -> tuple[str, Recipe]:
    text = apply_text_patch(recipe.text, patch)
    new = apply_recipe_patch(recipe, patch)
    new.text = text
    return text, new


def patch_word_count(patch: Patch) -> int:
    return len((patch.before + " " + patch.after).split())


def patch_guardrails(patch: Patch) -> list[str]:
    problems: list[str] = []
    if patch.manual_fix:
        return problems
    if patch_word_count(patch) > 60:
        problems.append("patch before+after exceeds 30 words per side")
    if "\n" in patch.before or "\n" in patch.after:
        problems.append("patch spans multiple lines/steps")
    if not patch.before or not patch.after:
        problems.append("patch has an empty span")
    return problems
