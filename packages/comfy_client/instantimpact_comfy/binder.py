"""Workflow template binder — never hand-build graphs at runtime."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

PLACEHOLDER_RE = re.compile(r"^\{\{([A-Z0-9_]+)\}\}$")
ANY_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def extract_placeholders(obj: Any, found: set[str] | None = None) -> set[str]:
    found = found if found is not None else set()
    if isinstance(obj, dict):
        for v in obj.values():
            extract_placeholders(v, found)
    elif isinstance(obj, list):
        for v in obj:
            extract_placeholders(v, found)
    elif isinstance(obj, str):
        for m in ANY_PLACEHOLDER_RE.finditer(obj):
            found.add(m.group(1))
    return found


def validate_placeholders(template: dict[str, Any], required: set[str]) -> list[str]:
    present = extract_placeholders(template)
    missing = sorted(required - present)
    errors: list[str] = []
    if missing:
        errors.append(f"Template missing required placeholders: {', '.join(missing)}")
    return errors


def _replace_in_value(value: Any, mapping: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {k: _replace_in_value(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace_in_value(v, mapping) for v in value]
    if isinstance(value, str):
        m = PLACEHOLDER_RE.match(value.strip())
        if m:
            key = m.group(1)
            if key not in mapping:
                raise KeyError(f"Missing substitution for {{{{{key}}}}}")
            return mapping[key]

        # Partial embed in longer strings
        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in mapping:
                raise KeyError(f"Missing substitution for {{{{{key}}}}}")
            return str(mapping[key])

        return ANY_PLACEHOLDER_RE.sub(repl, value)
    return value


def bind_workflow(template: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy template and substitute {{VAR}} placeholders."""
    bound = copy.deepcopy(template)
    return _replace_in_value(bound, variables)


def load_workflow(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def nodes_only(workflow: dict[str, Any]) -> dict[str, Any]:
    """Strip _meta and non-node keys before sending to Comfy /prompt."""
    return {k: v for k, v in workflow.items() if isinstance(v, dict) and "class_type" in v}


# Required keys for flux_still_character_v1 (CheckpointLoaderSimple / FP8 path)
FLUX_STILL_REQUIRED_VARS = {
    "CKPT_NAME",
    "POSITIVE_PROMPT",
    "NEGATIVE_PROMPT",
    "SEED",
    "WIDTH",
    "HEIGHT",
    "STEPS",
    "CFG",
    "GUIDANCE",
    "FILENAME_PREFIX",
}

# Base + character LoRA
FLUX_STILL_LORA_REQUIRED_VARS = FLUX_STILL_REQUIRED_VARS | {
    "LORA_NAME",
    "LORA_STRENGTH",
}
