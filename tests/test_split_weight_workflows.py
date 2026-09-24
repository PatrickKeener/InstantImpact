"""BF16 split-weight graphs must bind and bypass exactly like the fp8 ones."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from instantimpact_comfy.binder import (
    DETAIL_LORA_NODE_ID,
    DETAIL_LORA_OUTPUTS,
    DETAIL_LORA_VARS,
    FLUX_STILL_SPLIT_LORA_REQUIRED_VARS,
    FLUX_STILL_SPLIT_REQUIRED_VARS,
    HIRES_BYPASS_ORDER,
    HIRES_VARS,
    bind_workflow,
    bypass_node,
    load_workflow,
    nodes_only,
    validate_placeholders,
)
from worker.tasks.stills import _split_weight_vars, _use_split_weights

WORKFLOWS = ROOT / "workflows"

BASE_VARS = {
    "CLIP_L_PROMPT": "auburn hair, portrait",
    "POSITIVE_PROMPT": "a photo of a woman in a sunlit meadow",
    "NEGATIVE_PROMPT": "",
    "SEED": 42,
    "WIDTH": 1024,
    "HEIGHT": 1280,
    "STEPS": 28,
    "CFG": 1.0,
    "GUIDANCE": 2.5,
    "SAMPLER_NAME": "euler",
    "SCHEDULER": "simple",
    "FILENAME_PREFIX": "ii_test_000",
}
LORA_VARS = {"LORA_NAME": "zoe.safetensors", "LORA_STRENGTH": 0.85, "LORA_CLIP_STRENGTH": 0.55}
DETAIL_VARS = {"DETAIL_LORA_NAME": "detail.safetensors", "DETAIL_LORA_STRENGTH": 0.6}
HIRES_VALUES = {
    "HIRES_WIDTH": 1536,
    "HIRES_HEIGHT": 1920,
    "HIRES_DENOISE": 0.4,
    "HIRES_SAMPLER_NAME": "euler",
    "HIRES_SCHEDULER": "simple",
}


@pytest.mark.parametrize(
    ("name", "required", "extra"),
    [
        ("flux_still_character_split_v1.json", FLUX_STILL_SPLIT_REQUIRED_VARS, {}),
        (
            "flux_still_character_lora_split_v1.json",
            FLUX_STILL_SPLIT_LORA_REQUIRED_VARS,
            LORA_VARS,
        ),
    ],
)
def test_split_template_binds_with_every_optional_stage(name, required, extra):
    template = load_workflow(WORKFLOWS / name)
    assert validate_placeholders(template, required | DETAIL_LORA_VARS | HIRES_VARS) == []

    graph = nodes_only(
        bind_workflow(
            template,
            {**BASE_VARS, **extra, **DETAIL_VARS, **HIRES_VALUES, **_split_weight_vars()},
        )
    )
    assert graph["20"]["class_type"] == "UNETLoader"
    assert graph["21"]["inputs"]["type"] == "flux"
    assert graph["8"]["inputs"]["vae"] == ["22", 0]
    # CheckpointLoaderSimple's null clip is the whole reason this path exists.
    assert not any(n["class_type"] == "CheckpointLoaderSimple" for n in graph.values())
    assert "{{" not in str(graph)


@pytest.mark.parametrize(
    ("name", "required", "extra"),
    [
        ("flux_still_character_split_v1.json", FLUX_STILL_SPLIT_REQUIRED_VARS, {}),
        (
            "flux_still_character_lora_split_v1.json",
            FLUX_STILL_SPLIT_LORA_REQUIRED_VARS,
            LORA_VARS,
        ),
    ],
)
def test_split_template_binds_with_detail_lora_and_hires_bypassed(name, required, extra):
    template = load_workflow(WORKFLOWS / name)
    template = bypass_node(template, DETAIL_LORA_NODE_ID, DETAIL_LORA_OUTPUTS)
    for node_id, outputs in HIRES_BYPASS_ORDER:
        template = bypass_node(template, node_id, outputs)
    assert validate_placeholders(template, required) == []

    graph = nodes_only(bind_workflow(template, {**BASE_VARS, **extra, **_split_weight_vars()}))
    assert DETAIL_LORA_NODE_ID not in graph
    assert graph["8"]["inputs"]["samples"] == ["3", 0]
    # Text encoders fall back to the loader (or character LoRA) that fed node 12.
    expected_clip = ["10", 1] if extra else ["21", 0]
    assert graph["6"]["inputs"]["clip"] == expected_clip
    assert "{{" not in str(graph)


def test_split_loader_is_opt_in(monkeypatch):
    monkeypatch.delenv("INSTANTIMPACT_COMFY_LOADER", raising=False)
    assert _use_split_weights() is False
    monkeypatch.setenv("INSTANTIMPACT_COMFY_LOADER", "split")
    assert _use_split_weights() is True
    monkeypatch.setenv("INSTANTIMPACT_COMFY_LOADER", "checkpoint")
    assert _use_split_weights() is False


def test_split_weight_vars_are_overridable(monkeypatch):
    monkeypatch.delenv("INSTANTIMPACT_COMFY_CLIP_NAME2", raising=False)
    assert _split_weight_vars()["CLIP_NAME2"] == "t5xxl_fp16.safetensors"
    monkeypatch.setenv("INSTANTIMPACT_COMFY_CLIP_NAME2", "t5xxl_fp8_e4m3fn.safetensors")
    assert _split_weight_vars()["CLIP_NAME2"] == "t5xxl_fp8_e4m3fn.safetensors"
