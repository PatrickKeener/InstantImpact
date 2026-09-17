"""Ostris AI Toolkit path resolution + Flux LoRA YAML (no PyYAML required)."""

from __future__ import annotations

import os
from pathlib import Path


def _is_toolkit_root(path: Path) -> bool:
    return path.is_dir() and (path / "run.py").is_file()


def resolve_toolkit_dir(explicit: str | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    env = os.environ.get("INSTANTIMPACT_AI_TOOLKIT_DIR")
    if env:
        candidates.append(Path(env).expanduser())
    home = Path.home()
    candidates.extend(
        [
            home / "ai-toolkit",
            Path("/home/pkeener/ai-toolkit"),
            Path("/opt/ai-toolkit"),
        ]
    )
    seen: set[str] = set()
    for c in candidates:
        key = str(c)
        if key in seen:
            continue
        seen.add(key)
        try:
            resolved = c.resolve()
        except OSError:
            continue
        if _is_toolkit_root(resolved):
            return resolved
    return None


def _python_has_torchaudio(python: Path) -> bool:
    if not python.is_file():
        return False
    try:
        import subprocess

        r = subprocess.run(
            [str(python), "-c", "import torchaudio"],
            capture_output=True,
            timeout=20,
        )
        return r.returncode == 0
    except Exception:
        return False


def resolve_toolkit_python(toolkit_dir: Path) -> Path:
    """Pick a toolkit interpreter that can import torchaudio (Ostris uses venv/, not .venv/)."""
    candidates: list[Path] = []
    env_py = os.environ.get("INSTANTIMPACT_AI_TOOLKIT_PYTHON")
    if env_py:
        candidates.append(Path(env_py).expanduser())
    candidates.extend(
        [
            toolkit_dir / "venv" / "bin" / "python",
            toolkit_dir / ".venv" / "bin" / "python",
            toolkit_dir / "venv" / "Scripts" / "python.exe",
            toolkit_dir / ".venv" / "Scripts" / "python.exe",
        ]
    )
    existing = [p for p in candidates if p.is_file()]
    for p in existing:
        if _python_has_torchaudio(p):
            return p
    if existing:
        return existing[0]
    return Path(env_py or "python3")


def _yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render_flux_lora_yaml(
    *,
    name: str,
    trigger_word: str,
    dataset_dir: str,
    training_folder: str,
    steps: int = 1500,
    lr: str = "1e-4",
    linear: int = 16,
) -> str:
    """AI Toolkit extension job YAML, matching the Sienna/nemesis Flux LoRA recipe."""
    name = _yaml_escape(name)
    trigger = _yaml_escape(trigger_word)
    dataset = _yaml_escape(dataset_dir.replace("\\", "/"))
    folder = _yaml_escape(training_folder.replace("\\", "/"))
    steps = max(200, min(int(steps), 4000))
    return f"""---
job: extension
config:
  name: "{name}"
  process:
    - type: "sd_trainer"
      training_folder: "{folder}"
      device: cuda:0
      trigger_word: "{trigger}"
      network:
        type: "lora"
        linear: {linear}
        linear_alpha: {linear}
      save:
        dtype: float16
        save_every: 250
        max_step_saves_to_keep: 4
        push_to_hub: false
      datasets:
        - folder_path: "{dataset}"
          caption_ext: "txt"
          caption_dropout_rate: 0.05
          shuffle_tokens: false
          cache_latents_to_disk: true
          resolution: [512, 768, 1024]
      train:
        batch_size: 1
        steps: {steps}
        gradient_accumulation_steps: 1
        train_unet: true
        train_text_encoder: false
        gradient_checkpointing: true
        noise_scheduler: "flowmatch"
        optimizer: "adamw8bit"
        lr: {lr}
        ema_config:
          use_ema: true
          ema_decay: 0.99
        dtype: bf16
      model:
        name_or_path: "black-forest-labs/FLUX.1-dev"
        is_flux: true
        quantize: true
      sample:
        sampler: "flowmatch"
        sample_every: 250
        sample_start_step: 0
        width: 1024
        height: 1280
        prompts:
          - "[trigger], photorealistic portrait of an adult woman, mid-20s, natural window light, 85mm photo"
          - "[trigger], adult woman casual bedroom, oversized tee, soft daylight, lifestyle photograph"
          - "[trigger], adult woman looking at camera, natural skin texture, professional photography"
        neg: ""
        seed: 42
        walk_seed: true
        guidance_scale: 4
        sample_steps: 20
meta:
  name: "[name]"
  version: "1.0"
  instantimpact_trigger: "{trigger}"
"""


def find_trained_weights(training_folder: Path, name: str) -> Path | None:
    if not training_folder.is_dir():
        return None
    skip = ("optimizer", "ema-only")
    named = [
        p
        for p in training_folder.rglob(f"{name}.safetensors")
        if p.is_file() and not any(s in p.name.lower() for s in skip)
    ]
    if named:
        return max(named, key=lambda p: p.stat().st_mtime)
    all_s = [
        p
        for p in training_folder.rglob("*.safetensors")
        if p.is_file() and not any(s in p.name.lower() for s in skip)
    ]
    if not all_s:
        return None
    return max(all_s, key=lambda p: (p.stat().st_mtime, p.stat().st_size))
