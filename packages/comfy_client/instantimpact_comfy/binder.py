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


def bypass_node(
    workflow: dict[str, Any], node_id: str, output_map: dict[int, str]
) -> dict[str, Any]:
    """Remove an optional node and rewire its consumers to its own upstream inputs.

    `output_map` maps each of the node's output slots to the input key that
    passes through it, e.g. a LoraLoader is {0: "model", 1: "clip"}. Used for
    slots that are only present when an operator configured a weight file, so
    templates stay reviewable instead of multiplying per combination.
    """
    node = workflow.get(node_id)
    if not isinstance(node, dict):
        return workflow
    sources = {slot: node.get("inputs", {})[key] for slot, key in output_map.items()}
    pruned = {k: v for k, v in workflow.items() if k != node_id}

    def rewire(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: rewire(v) for k, v in value.items()}
        if isinstance(value, list):
            if len(value) == 2 and value[0] == node_id and isinstance(value[1], int):
                return sources[value[1]]
            return [rewire(v) for v in value]
        return value

    return rewire(pruned)


# Required keys for flux_still_character_v1 (CheckpointLoaderSimple / FP8 path)
FLUX_STILL_REQUIRED_VARS = {
    "CKPT_NAME",
    "CLIP_L_PROMPT",
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

# Base + character LoRA (clip strength is lower so the shot request is not overwritten)
FLUX_STILL_LORA_REQUIRED_VARS = FLUX_STILL_REQUIRED_VARS | {
    "LORA_NAME",
    "LORA_STRENGTH",
    "LORA_CLIP_STRENGTH",
}

# Optional anatomy/realism LoRA chained after the character LoRA. Bypassed via
# bypass_node when no weight file is configured.
DETAIL_LORA_NODE_ID = "12"
DETAIL_LORA_OUTPUTS = {0: "model", 1: "clip"}
DETAIL_LORA_VARS = {"DETAIL_LORA_NAME", "DETAIL_LORA_STRENGTH"}
