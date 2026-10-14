"""Install character LoRAs where ComfyUI's LoraLoader looks for them."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def comfy_lora_filename(slug: str, version_int: int) -> str:
    safe = str(slug).strip()
    if not safe or any(ch in safe for ch in ("/", "\\", "\0")):
        raise ValueError(f"Invalid character slug for LoRA filename: {slug!r}")
    return f"ii_{safe}_v{int(version_int):03d}.safetensors"


def install_character_lora(src: Path, loras_dir: Path, filename: str) -> Path:
    """Copy weights into the Comfy LoRA directory and publish them atomically.

    A generation job can only see a complete file: the copy lands under a
    temporary name and replaces the final filename in one step.
    """
    source = Path(src).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"LoRA weights not found: {source}")
    if source.stat().st_size <= 0:
        raise OSError(f"LoRA weights are empty: {source}")
    if not _safe_filename(filename):
        raise ValueError(f"Invalid LoRA filename: {filename!r}")

    folder = Path(loras_dir).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    if source.resolve() == target.resolve():
        return target

    tmp = folder / f".{filename}.{os.getpid()}.partial"
    try:
        shutil.copy2(source, tmp)
        if tmp.stat().st_size != source.stat().st_size:
            raise OSError(f"LoRA copy size mismatch for {filename}")
        os.replace(tmp, target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    if not target.is_file() or target.stat().st_size <= 0:
        raise OSError(f"LoRA install did not produce {target}")
    return target


def character_lora_problem(name: str | None, loras_dir: str | Path | None) -> str | None:
    """Return an operator-facing error when a registered LoRA is not loadable."""
    if not name:
        return None
    if not loras_dir:
        return (
            f"Character LoRA {name} is registered but INSTANTIMPACT_COMFY_LORAS_DIR is not set."
        )
    path = Path(loras_dir).expanduser() / name
    if path.is_file() and path.stat().st_size > 0:
        return None
    return (
        f"Character LoRA is not installed: {path}. "
        "Train the character again, or copy its model.safetensors to that path."
    )


def ensure_character_lora(
    name: str | None,
    source: str | Path | None,
    loras_dir: str | Path | None,
) -> str | None:
    """Install from the saved character weights when Comfy's copy is missing.

    Returns None when generation can load the LoRA, or one error string.
    """
    problem = character_lora_problem(name, loras_dir)
    if problem is None or not name or not loras_dir or source is None:
        return problem
    src = Path(source).expanduser()
    if not src.is_file():
        return problem
    try:
        install_character_lora(src, Path(loras_dir), name)
    except OSError as exc:
        return f"Could not install character LoRA {name} into {loras_dir}: {exc}"
    return character_lora_problem(name, loras_dir)


def _safe_filename(filename: str) -> bool:
    if not filename or filename.startswith("."):
        return False
    return "/" not in filename and "\\" not in filename and "\0" not in filename
