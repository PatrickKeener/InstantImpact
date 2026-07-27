from pathlib import Path

from instantimpact_comfy.binder import (
    FLUX_STILL_REQUIRED_VARS,
    bind_workflow,
    extract_placeholders,
    load_workflow,
    validate_placeholders,
)


def test_flux_template_has_required_placeholders():
    root = Path(__file__).resolve().parents[1]
    wf = load_workflow(root / "workflows" / "flux_still_character_v1.json")
    errors = validate_placeholders(wf, FLUX_STILL_REQUIRED_VARS)
    assert errors == []


def test_bind_workflow_substitutes():
    template = {
        "1": {"class_type": "X", "inputs": {"text": "{{POSITIVE_PROMPT}}", "seed": "{{SEED}}"}}
    }
    bound = bind_workflow(template, {"POSITIVE_PROMPT": "hello", "SEED": 42})
    assert bound["1"]["inputs"]["text"] == "hello"
    assert bound["1"]["inputs"]["seed"] == 42
    assert "POSITIVE_PROMPT" in extract_placeholders(template)
