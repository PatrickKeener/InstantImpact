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


def test_detail_lora_is_chained_before_sampler():
    from instantimpact_comfy.binder import DETAIL_LORA_NODE_ID, FLUX_STILL_LORA_REQUIRED_VARS

    root = Path(__file__).resolve().parents[1]
    wf = load_workflow(root / "workflows" / "flux_still_character_lora_v1.json")
    detail = wf[DETAIL_LORA_NODE_ID]
    assert detail["class_type"] == "LoraLoader"
    # Chained after the character LoRA so identity still applies
    assert detail["inputs"]["model"] == ["10", 0]
    # Text encoding is untouched so the detail LoRA cannot fight prompt adherence
    assert detail["inputs"]["strength_clip"] == 0.0
    sampler = next(n for n in wf.values() if n.get("class_type") == "KSampler")
    assert sampler["inputs"]["model"] == [DETAIL_LORA_NODE_ID, 0]
    errors = validate_placeholders(wf, FLUX_STILL_LORA_REQUIRED_VARS)
    assert errors == []


def test_bypass_detail_lora_rewires_to_character_lora():
    from instantimpact_comfy.binder import (
        DETAIL_LORA_NODE_ID,
        DETAIL_LORA_OUTPUTS,
        FLUX_STILL_LORA_REQUIRED_VARS,
        bypass_node,
        extract_placeholders,
    )

    root = Path(__file__).resolve().parents[1]
    wf = load_workflow(root / "workflows" / "flux_still_character_lora_v1.json")
    pruned = bypass_node(wf, DETAIL_LORA_NODE_ID, DETAIL_LORA_OUTPUTS)

    assert DETAIL_LORA_NODE_ID not in pruned
    encode = next(n for n in pruned.values() if n.get("class_type") == "CLIPTextEncodeFlux")
    assert pruned["3"]["inputs"]["model"] == ["10", 0]
    assert pruned["14"]["inputs"]["model"] == ["10", 0]
    assert encode["inputs"]["clip"] == ["10", 1]
    # No dangling placeholders for the slot we removed
    placeholders = extract_placeholders(pruned)
    assert "DETAIL_LORA_NAME" not in placeholders
    assert validate_placeholders(pruned, FLUX_STILL_LORA_REQUIRED_VARS) == []


def test_bypass_detail_lora_in_base_graph_rewires_to_checkpoint():
    from instantimpact_comfy.binder import (
        DETAIL_LORA_NODE_ID,
        DETAIL_LORA_OUTPUTS,
        bypass_node,
    )

    root = Path(__file__).resolve().parents[1]
    wf = load_workflow(root / "workflows" / "flux_still_character_v1.json")
    pruned = bypass_node(wf, DETAIL_LORA_NODE_ID, DETAIL_LORA_OUTPUTS)
    assert pruned["3"]["inputs"]["model"] == ["4", 0]
    assert pruned["14"]["inputs"]["model"] == ["4", 0]


def test_hires_pass_refines_the_base_latent_with_shared_conditioning():
    root = Path(__file__).resolve().parents[1]
    wf = load_workflow(root / "workflows" / "flux_still_character_lora_v1.json")

    assert wf["13"]["inputs"]["samples"] == ["3", 0]
    assert wf["14"]["inputs"]["latent_image"] == ["13", 0]
    assert wf["14"]["inputs"]["positive"] == wf["3"]["inputs"]["positive"]
    assert wf["14"]["inputs"]["negative"] == wf["3"]["inputs"]["negative"]
    assert wf["8"]["inputs"]["samples"] == ["14", 0]


def test_bypassing_hires_falls_back_to_the_base_latent():
    from instantimpact_comfy.binder import (
        FLUX_STILL_LORA_REQUIRED_VARS,
        HIRES_BYPASS_ORDER,
        bypass_node,
        extract_placeholders,
    )

    root = Path(__file__).resolve().parents[1]
    wf = load_workflow(root / "workflows" / "flux_still_character_lora_v1.json")
    for node_id, outputs in HIRES_BYPASS_ORDER:
        wf = bypass_node(wf, node_id, outputs)

    assert "13" not in wf and "14" not in wf
    assert wf["8"]["inputs"]["samples"] == ["3", 0]
    placeholders = extract_placeholders(wf)
    assert "HIRES_WIDTH" not in placeholders
    assert "HIRES_DENOISE" not in placeholders
    assert validate_placeholders(wf, FLUX_STILL_LORA_REQUIRED_VARS) == []


def test_hires_and_detail_lora_can_both_be_bypassed():
    from instantimpact_comfy.binder import (
        DETAIL_LORA_NODE_ID,
        DETAIL_LORA_OUTPUTS,
        FLUX_STILL_REQUIRED_VARS,
        HIRES_BYPASS_ORDER,
        bypass_node,
    )

    root = Path(__file__).resolve().parents[1]
    wf = load_workflow(root / "workflows" / "flux_still_character_v1.json")
    wf = bypass_node(wf, DETAIL_LORA_NODE_ID, DETAIL_LORA_OUTPUTS)
    for node_id, outputs in HIRES_BYPASS_ORDER:
        wf = bypass_node(wf, node_id, outputs)

    assert wf["8"]["inputs"]["samples"] == ["3", 0]
    assert wf["3"]["inputs"]["model"] == ["4", 0]
    assert validate_placeholders(wf, FLUX_STILL_REQUIRED_VARS) == []


def test_bind_workflow_substitutes():
    template = {
        "1": {"class_type": "X", "inputs": {"text": "{{POSITIVE_PROMPT}}", "seed": "{{SEED}}"}}
    }
    bound = bind_workflow(template, {"POSITIVE_PROMPT": "hello", "SEED": 42})
    assert bound["1"]["inputs"]["text"] == "hello"
    assert bound["1"]["inputs"]["seed"] == 42
    assert "POSITIVE_PROMPT" in extract_placeholders(template)
