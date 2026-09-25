"""Local Comfy weight/node inventory for the Flux still pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

KIND_DIRS: dict[str, tuple[str, ...]] = {
    "checkpoints": ("models/checkpoints",),
    "diffusion_models": ("models/diffusion_models", "models/unet"),
    "clip": ("models/clip", "models/text_encoders"),
    "vae": ("models/vae",),
    "loras": ("models/loras",),
    "upscale_models": ("models/upscale_models",),
    "pulid": ("models/pulid",),
}

CORE_NODES = (
    "CLIPTextEncodeFlux",
    "KSampler",
    "VAEDecode",
    "VAEEncode",
    "EmptyLatentImage",
    "SaveImage",
    "LoraLoader",
    "ImageScale",
    "ImageUpscaleWithModel",
    "UpscaleModelLoader",
)
SPLIT_NODES = ("UNETLoader", "DualCLIPLoader", "VAELoader")
CHECKPOINT_NODES = ("CheckpointLoaderSimple",)
STILL_JOB_TYPES = frozenset({"seed_gallery", "still_batch", "validation_sheet"})


@dataclass(frozen=True)
class FluxRuntime:
    mock: bool
    comfy_enabled: bool
    loader: str
    comfy_root: Path | None
    ckpt_name: str
    unet_name: str
    clip_name1: str
    clip_name2: str
    vae_name: str
    detail_lora_name: str | None = None
    upscale_model_name: str | None = None
    pulid_model_name: str | None = None


def _optional(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def resolve_comfy_root(*candidates: str | Path | None) -> Path | None:
    paths: list[Path] = []
    for raw in candidates:
        if raw:
            paths.append(Path(str(raw)).expanduser())
    env = os.environ.get("INSTANTIMPACT_COMFY_DIR")
    if env:
        paths.append(Path(env).expanduser())
    home = Path.home()
    paths.extend(
        [
            home / "ComfyUI",
            Path("/home/pkeener/ComfyUI"),
        ]
    )
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if (resolved / "main.py").is_file() or (resolved / "models").is_dir():
            return resolved
    return None


def find_model(comfy_root: Path | None, kind: str, filename: str) -> Path | None:
    name = (filename or "").strip()
    if not comfy_root or not name:
        return None
    wanted = name.lower()
    for rel in KIND_DIRS.get(kind, (f"models/{kind}",)):
        folder = comfy_root / rel
        direct = folder / name
        if direct.is_file():
            return direct
        hit = _match_filename(folder, wanted)
        if hit is not None:
            return hit
    models = comfy_root / "models"
    if models.is_dir():
        hit = _match_filename(models, wanted, depth=2)
        if hit is not None:
            return hit
    return None


def _match_filename(folder: Path, wanted: str, *, depth: int = 1) -> Path | None:
    if not folder.is_dir() or depth < 0:
        return None
    try:
        entries = list(folder.iterdir())
    except OSError:
        return None
    for entry in entries:
        if entry.is_file() and entry.name.lower() == wanted:
            return entry
    if depth == 0:
        return None
    for entry in entries:
        if entry.is_dir():
            hit = _match_filename(entry, wanted, depth=depth - 1)
            if hit is not None:
                return hit
    return None


def runtime_from_env(
    getenv: Callable[[str], str | None] | None = None,
    *,
    comfy_root: Path | None = None,
) -> FluxRuntime:
    get = getenv or os.environ.get
    loader = (get("INSTANTIMPACT_COMFY_LOADER") or "checkpoint").strip().lower()
    mock_raw = (get("INSTANTIMPACT_MOCK_GENERATION") or "true").strip().lower()
    enabled_raw = (get("INSTANTIMPACT_COMFY_ENABLED") or "false").strip().lower()
    env_dir = get("INSTANTIMPACT_COMFY_DIR")
    root = comfy_root if comfy_root is not None else resolve_comfy_root(env_dir)
    return FluxRuntime(
        mock=mock_raw in {"1", "true", "yes"},
        comfy_enabled=enabled_raw in {"1", "true", "yes"},
        loader=loader,
        comfy_root=root,
        ckpt_name=(get("INSTANTIMPACT_COMFY_CKPT_NAME") or "flux1-dev-fp8.safetensors").strip(),
        unet_name=(get("INSTANTIMPACT_COMFY_UNET_NAME") or "flux1-dev.safetensors").strip(),
        clip_name1=(get("INSTANTIMPACT_COMFY_CLIP_NAME1") or "clip_l.safetensors").strip(),
        clip_name2=(get("INSTANTIMPACT_COMFY_CLIP_NAME2") or "t5xxl_fp16.safetensors").strip(),
        vae_name=(get("INSTANTIMPACT_COMFY_VAE_NAME") or "ae.safetensors").strip(),
        detail_lora_name=_optional(get("INSTANTIMPACT_DETAIL_LORA_NAME")),
        upscale_model_name=_optional(get("INSTANTIMPACT_COMFY_UPSCALE_MODEL")),
        pulid_model_name=_optional(get("INSTANTIMPACT_PULID_MODEL")),
    )


def _use_split(loader: str) -> bool:
    return loader in {"split", "unet", "diffusion_model"}


def _file_entry(kind: str, name: str, path: Path | None) -> dict[str, Any]:
    return {
        "kind": kind,
        "name": name,
        "path": str(path) if path else None,
        "present": path is not None,
    }


def inspect_flux_still(
    runtime: FluxRuntime,
    *,
    object_info: dict[str, Any] | None = None,
    comfy_reachable: bool | None = None,
) -> dict[str, Any]:
    """Return pipeline status: mock | ok | unreachable | missing_weights | missing_nodes."""
    if runtime.mock or not runtime.comfy_enabled:
        return {
            "status": "mock",
            "loader": runtime.loader,
            "comfy_root": str(runtime.comfy_root) if runtime.comfy_root else None,
            "missing_weights": [],
            "missing_nodes": [],
            "optional_missing": [],
            "files": [],
            "unverified": False,
        }

    required: list[tuple[str, str]] = []
    if _use_split(runtime.loader):
        required.extend(
            [
                ("diffusion_models", runtime.unet_name),
                ("clip", runtime.clip_name1),
                ("clip", runtime.clip_name2),
                ("vae", runtime.vae_name),
            ]
        )
        node_names: tuple[str, ...] = CORE_NODES + SPLIT_NODES
    else:
        required.append(("checkpoints", runtime.ckpt_name))
        node_names = CORE_NODES + CHECKPOINT_NODES

    files: list[dict[str, Any]] = []
    missing_weights: list[str] = []
    unverified = runtime.comfy_root is None
    if not unverified:
        for kind, name in required:
            path = find_model(runtime.comfy_root, kind, name)
            files.append(_file_entry(kind, name, path))
            if path is None:
                missing_weights.append(name)

    optional: list[tuple[str, str]] = []
    if runtime.detail_lora_name:
        optional.append(("loras", runtime.detail_lora_name))
    if runtime.upscale_model_name:
        optional.append(("upscale_models", runtime.upscale_model_name))
    if runtime.pulid_model_name:
        optional.append(("pulid", runtime.pulid_model_name))
    optional_missing: list[str] = []
    for kind, name in optional:
        path = find_model(runtime.comfy_root, kind, name) if not unverified else None
        files.append(_file_entry(kind, name, path))
        if not unverified and path is None:
            optional_missing.append(name)

    missing_nodes: list[str] = []
    if object_info is not None:
        present = set(object_info)
        missing_nodes = [n for n in node_names if n not in present]
        if runtime.pulid_model_name:
            for n in ("ApplyPulidFlux", "PulidFluxModelLoader"):
                if n not in present:
                    missing_nodes.append(n)

    if comfy_reachable is False:
        # Worker starts Comfy per job. Down at idle is fine when weights exist.
        status = "missing_weights" if missing_weights else "idle"
    elif missing_nodes:
        status = "missing_nodes"
    elif missing_weights:
        status = "missing_weights"
    elif unverified:
        status = "ok"
    else:
        status = "ok"

    return {
        "status": status,
        "loader": runtime.loader,
        "comfy_root": str(runtime.comfy_root) if runtime.comfy_root else None,
        "missing_weights": missing_weights,
        "missing_nodes": missing_nodes,
        "optional_missing": optional_missing,
        "files": files,
        "unverified": unverified,
        "unet": runtime.unet_name if _use_split(runtime.loader) else runtime.ckpt_name,
    }


def fail_closed_message(report: dict[str, Any]) -> str | None:
    status = report.get("status")
    if status in {"mock", "ok", "idle"}:
        return None
    if status == "unreachable":
        return (
            "ComfyUI is not reachable. Start it on INSTANTIMPACT_COMFY_URL "
            "before generating stills."
        )
    if status == "missing_nodes":
        nodes = ", ".join(report.get("missing_nodes") or [])
        return f"ComfyUI is missing Flux still nodes: {nodes}"
    missing = ", ".join(report.get("missing_weights") or [])
    loader = report.get("loader") or "checkpoint"
    profile = "krea" if "krea" in str(report.get("unet") or "").lower() else (
        "bf16" if loader in {"split", "unet", "diffusion_model"} else "fp8"
    )
    root = report.get("comfy_root") or "$INSTANTIMPACT_COMFY_DIR"
    return (
        f"Flux still pipeline missing weights: {missing}. "
        f"Looked under {root}. "
        f"On the GPU host run: python scripts/bootstrap_models.py --profile {profile} "
        "--i-accept-licenses"
    )


def stills_require_pipeline(job_type: str) -> bool:
    return job_type in STILL_JOB_TYPES


def dest_dir_for_kind(comfy_root: Path, kind: str) -> Path:
    rel = KIND_DIRS.get(kind, (f"models/{kind}",))[0]
    return comfy_root / rel


def hf_url(repo: str, path: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/main/{path}"


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def iter_required_names(runtime: FluxRuntime) -> Iterable[tuple[str, str]]:
    if _use_split(runtime.loader):
        yield "diffusion_models", runtime.unet_name
        yield "clip", runtime.clip_name1
        yield "clip", runtime.clip_name2
        yield "vae", runtime.vae_name
    else:
        yield "checkpoints", runtime.ckpt_name
