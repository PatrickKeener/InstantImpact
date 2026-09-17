"""LoRA train job — Ostris AI Toolkit under the GPU lock. No SQLite."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import shutil
from pathlib import Path
from typing import Any

from worker.gpu_lock import GpuLock, is_cancel_requested


async def process_lora_train(ctx: dict[str, Any], job_id: str, request_path: str) -> dict[str, Any]:
    redis = ctx["redis"]
    path = Path(request_path)
    if not path.is_file():
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "missing_request",
                "message": f"request.json not found: {request_path}",
            },
        )
        return {"ok": False}

    snapshot = json.loads(path.read_text(encoding="utf-8"))
    lock = GpuLock(redis, holder_id=job_id)
    acquired = await lock.acquire(timeout=14400.0)
    if not acquired:
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "gpu_busy",
                "message": "Could not acquire GPU lock for LoRA train",
            },
        )
        return {"ok": False}

    try:
        await _publish(redis, {"job_id": job_id, "event": "running", "message": "GPU acquired — training LoRA"})
        return await _run_train(redis, snapshot, request_path=path)
    finally:
        await lock.release()


async def _run_train(redis: Any, snapshot: dict, *, request_path: Path) -> dict:
    from instantimpact_common.toolkit import (
        find_trained_weights,
        render_flux_lora_yaml,
        resolve_toolkit_dir,
        resolve_toolkit_python,
    )

    job_id = snapshot["job_id"]
    meta = snapshot.get("meta") or {}
    dataset_dir = _resolve_data(meta, "dataset_dir", "dataset_rel")
    dest_path = _resolve_data(meta, "dest_path", "dest_rel")
    training_folder = _resolve_data(meta, "training_folder", "training_rel")
    trigger = snapshot.get("trigger_word") or meta.get("trigger_word") or "sks_persona_v1"
    name = meta.get("run_name") or f"ii_{job_id[:8]}"
    steps = int(meta.get("steps") or 1500)

    if not dataset_dir.is_dir():
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "missing_dataset",
                "message": f"Dataset folder not found: {dataset_dir}",
            },
        )
        return {"ok": False}

    images = [
        p
        for p in dataset_dir.iterdir()
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    if len(images) < 4:
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "dataset_too_small",
                "message": f"Need at least 4 dataset images (have {len(images)})",
            },
        )
        return {"ok": False}

    if not _cuda_available():
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "no_cuda",
                "message": (
                    "LoRA train needs a native CUDA worker. "
                    "docker stop instantimpact-worker ; "
                    "cd /home/pkeener/InstantImpact/apps/worker && ../../.venv/bin/python -m worker.main"
                ),
            },
        )
        return {"ok": False}

    toolkit_dir = resolve_toolkit_dir(os.environ.get("INSTANTIMPACT_AI_TOOLKIT_DIR"))
    if not toolkit_dir:
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "toolkit_missing",
                "message": (
                    "Ostris AI Toolkit not found. Clone it on nemesis and set "
                    "INSTANTIMPACT_AI_TOOLKIT_DIR (e.g. /home/pkeener/ai-toolkit)."
                ),
            },
        )
        return {"ok": False}

    python = resolve_toolkit_python(toolkit_dir)
    training_folder.mkdir(parents=True, exist_ok=True)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path = Path(request_path).parent / "train.yaml"
    yaml_path.write_text(
        render_flux_lora_yaml(
            name=name,
            trigger_word=str(trigger),
            dataset_dir=str(dataset_dir),
            training_folder=str(training_folder),
            steps=steps,
        ),
        encoding="utf-8",
    )

    await _free_gpu(redis, job_id)
    if await is_cancel_requested(redis, job_id):
        await _publish(redis, {"job_id": job_id, "event": "cancelled"})
        return {"ok": False, "cancelled": True}

    await _publish(
        redis,
        {
            "job_id": job_id,
            "event": "item_started",
            "item_index": 0,
            "message": f"AI Toolkit {steps} steps · {toolkit_dir}",
        },
    )

    env = os.environ.copy()
    hf = os.environ.get("INSTANTIMPACT_HF_TOKEN") or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if hf:
        env["HF_TOKEN"] = hf
        env["HUGGING_FACE_HUB_TOKEN"] = hf

    proc = await asyncio.create_subprocess_exec(
        str(python),
        "run.py",
        str(yaml_path),
        cwd=str(toolkit_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )

    log_tail: list[str] = []
    assert proc.stdout is not None
    while True:
        if await is_cancel_requested(redis, job_id):
            _kill_pg(proc.pid)
            try:
                await asyncio.wait_for(proc.wait(), timeout=20)
            except TimeoutError:
                _kill_pg(proc.pid, sig=signal.SIGKILL)
                await proc.wait()
            await _publish(redis, {"job_id": job_id, "event": "cancelled"})
            return {"ok": False, "cancelled": True}

        try:
            line_b = await asyncio.wait_for(proc.stdout.readline(), timeout=2.0)
        except TimeoutError:
            if proc.returncode is not None:
                break
            continue
        if not line_b:
            break
        line = line_b.decode("utf-8", errors="replace").rstrip()
        if not line:
            continue
        log_tail.append(line)
        if len(log_tail) > 40:
            log_tail = log_tail[-40:]
        if _is_progress_line(line):
            await _publish(
                redis,
                {
                    "job_id": job_id,
                    "event": "log",
                    "message": line[:400],
                },
            )

    rc = await proc.wait()
    if rc != 0:
        tail = "\n".join(log_tail[-15:])
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "train_failed",
                "message": f"AI Toolkit exited {rc}. Last log:\n{tail}",
            },
        )
        return {"ok": False}

    weights = find_trained_weights(training_folder, name)
    if not weights or not weights.is_file():
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "missing_weights",
                "message": f"Training finished but no .safetensors under {training_folder}",
            },
        )
        return {"ok": False}

    dest = dest_path if dest_path.suffix.lower() == ".safetensors" else dest_path / "model.safetensors"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if weights.resolve() != dest.resolve():
        shutil.copy2(weights, dest)

    rel = meta.get("dest_rel") or str(dest)
    await _publish(
        redis,
        {
            "job_id": job_id,
            "event": "item_done",
            "item_index": 0,
            "message": f"Wrote {dest}",
            "lora_path": rel,
        },
    )
    await _publish(
        redis,
        {
            "job_id": job_id,
            "event": "completed",
            "message": "LoRA train complete — registering",
            "lora_path": str(dest),
            "auto_register": True,
            "strength": float(meta.get("strength") or 0.85),
        },
    )
    return {"ok": True, "lora_path": str(dest)}


def _is_progress_line(line: str) -> bool:
    low = line.lower()
    return any(tok in low for tok in ("step", "loss", "saving", "epoch", "train"))


def _kill_pg(pid: int | None, sig: signal.Signals = signal.SIGTERM) -> None:
    if not pid:
        return
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        try:
            os.kill(pid, sig)
        except OSError:
            pass


async def _free_gpu(redis: Any, job_id: str) -> None:
    await _publish(redis, {"job_id": job_id, "event": "log", "message": "Freeing GPU (vLLM + Comfy unload)"})
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "stop",
            "vllm",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except Exception:
        pass
    comfy = os.environ.get("INSTANTIMPACT_COMFY_URL", "http://127.0.0.1:8188")
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{comfy.rstrip('/')}/free", json={"unload_models": True, "free_memory": True})
    except Exception:
        pass


def _cuda_available() -> bool:
    try:
        proc = __import__("subprocess").run(
            ["nvidia-smi"],
            capture_output=True,
            timeout=8,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _resolve_data(meta: dict, abs_key: str, rel_key: str) -> Path:
    env = os.environ.get("INSTANTIMPACT_DATA_DIR")
    rel = meta.get(rel_key)
    if env and rel:
        return Path(env) / str(rel).replace("\\", "/").lstrip("/")
    raw = meta.get(abs_key) or ""
    return Path(raw)


async def _publish(redis: Any, event: dict) -> None:
    payload = json.dumps(event)
    await redis.rpush("instantimpact:job_events", payload)
    await redis.publish("instantimpact:job_events", payload)
