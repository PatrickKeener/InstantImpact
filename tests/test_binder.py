from pathlib import Path

from instantimpact_comfy.binder import (
    FLUX_STILL_REQUIRED_VARS,
    bind_workflow,
    extract_placeholders,
    load_workflow,
    validate_placeholders,
)


def test_flux_template_has_required_placeholders():
    from instantimpact_comfy.binder import FLUX_STILL_LORA_REQUIRED_VARS

    root = Path(__file__).resolve().parents[1]
    wf = load_workflow(root / "workflows" / "flux_still_character_v1.json")
    errors = validate_placeholders(wf, FLUX_STILL_REQUIRED_VARS)
    assert errors == []
    wf_l = load_workflow(root / "workflows" / "flux_still_character_lora_v1.json")
    errors_l = validate_placeholders(wf_l, FLUX_STILL_LORA_REQUIRED_VARS)
    assert errors_l == []
    for template in (wf, wf_l):
        sampler = next(node for node in template.values() if node.get("class_type") == "KSampler")
        encode = next(
            node for node in template.values() if node.get("class_type") == "CLIPTextEncodeFlux"
        )
        assert encode["inputs"]["clip_l"] == "{{CLIP_L_PROMPT}}"
        assert encode["inputs"]["t5xxl"] == "{{POSITIVE_PROMPT}}"
        assert encode["inputs"]["guidance"] == "{{GUIDANCE}}"
        assert sampler["inputs"]["cfg"] == "{{CFG}}"
        assert sampler["inputs"]["positive"][0] in template
        assert template[sampler["inputs"]["positive"][0]]["class_type"] == "CLIPTextEncodeFlux"


def test_bind_workflow_substitutes():
    template = {
        "1": {"class_type": "X", "inputs": {"text": "{{POSITIVE_PROMPT}}", "seed": "{{SEED}}"}}
    }
    bound = bind_workflow(template, {"POSITIVE_PROMPT": "hello", "SEED": 42})
    assert bound["1"]["inputs"]["text"] == "hello"
    assert bound["1"]["inputs"]["seed"] == 42
    assert "POSITIVE_PROMPT" in extract_placeholders(template)
