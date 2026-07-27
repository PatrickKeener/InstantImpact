# Workflow templates

Application code **never** builds ComfyUI graphs at runtime.

1. Export a working graph from ComfyUI (API format).
2. Replace bindable values with `{{VAR_NAME}}` placeholders.
3. Pin custom node commit SHAs in `docs/model_cards.md`.
4. Health checks fail closed if required nodes are missing.

See design doc § Workflow Template Spec and `instantimpact_comfy.binder`.
