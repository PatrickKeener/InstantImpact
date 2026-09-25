"""ARQ worker entrypoint.

python -m worker.main
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
for p in (
    _REPO / "packages" / "common",
    _REPO / "packages" / "comfy_client",
    _REPO / "packages" / "prompt_engine",
    _REPO / "apps" / "worker",
    _REPO / "apps" / "api",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from arq.connections import RedisSettings

from worker.tasks.stills import process_still_job
from worker.tasks.train import process_lora_train


log = logging.getLogger("instantimpact.worker")


def configure_logging() -> None:
    """Attach a stdout handler.

    arq only configures logging in its own CLI, so `run_worker()` leaves the
    root logger bare: startup lines, task errors, and tracebacks all vanish and
    a crashing worker looks identical to an idle one.
    """
    level = (os.environ.get("INSTANTIMPACT_LOG_LEVEL") or "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )


async def run_generation_job(ctx, job_id: str, request_path: str, job_type: str):
    log.info("job start id=%s type=%s request=%s", job_id, job_type, request_path)
    try:
        if job_type == "lora_train":
            result = await process_lora_train(ctx, job_id, request_path)
        else:
            result = await process_still_job(ctx, job_id, request_path, job_type)
    except Exception:
        # arq records the failure, but without this the traceback is never shown.
        log.exception("job crashed id=%s type=%s", job_id, job_type)
        raise
    log.info("job end id=%s result=%s", job_id, result)
    return result


def _job_timeout() -> float:
    """Outer backstop for a whole job, which must outlast every inner timeout.

    A job is a full batch (seed galleries allow up to 40 stills) or a LoRA
    training run, so arq's 300s default cuts real work off mid-batch. The inner
    timeouts do the actual bounding: ComfyClient gives each prompt
    INSTANTIMPACT_COMFY_TIMEOUT and a per-item failure is caught and skipped.
    This only needs to catch a wedged process, so it matches the 4h GPU lock
    ceiling used by the training task.
    """
    raw = (os.environ.get("INSTANTIMPACT_JOB_TIMEOUT") or "").strip()
    try:
        return float(raw) if raw else 14400.0
    except ValueError:
        return 14400.0


class WorkerSettings:
    functions = [run_generation_job]
    redis_settings = RedisSettings(host="127.0.0.1", port=6379)
    queue_name = "instantimpact"
    max_jobs = 1  # serialize heavy work; GPU lock also enforces single job
    job_timeout = _job_timeout()


def _weights_summary() -> str:
    """Describe the weights actually in play.

    Logging the checkpoint name unconditionally is misleading on the split
    path, where that variable is ignored entirely.
    """
    from worker.tasks.stills import _split_weight_vars, _use_split_weights

    if not _use_split_weights():
        ckpt = os.environ.get("INSTANTIMPACT_COMFY_CKPT_NAME", "flux1-dev-fp8.safetensors")
        return f"loader=checkpoint ckpt={ckpt}"
    v = _split_weight_vars()
    return (
        f"loader=split unet={v['UNET_NAME']} dtype={v['UNET_WEIGHT_DTYPE']} "
        f"clip={v['CLIP_NAME1']}+{v['CLIP_NAME2']} vae={v['VAE_NAME']}"
    )


def main() -> None:
    from arq.worker import run_worker

    configure_logging()
    redis_url = os.environ.get("INSTANTIMPACT_REDIS_URL", "redis://127.0.0.1:6379/0")
    # parse host/port simply
    host, port = "127.0.0.1", 6379
    if redis_url.startswith("redis://"):
        rest = redis_url[len("redis://") :].split("/")[0]
        if ":" in rest:
            host, port_s = rest.split(":")
            port = int(port_s)
        else:
            host = rest or host
    WorkerSettings.redis_settings = RedisSettings(host=host, port=port)
    log.info(
        "worker starting queue=%s redis=%s:%s comfy=%s data=%s workflows=%s timeout=%ss",
        WorkerSettings.queue_name,
        host,
        port,
        os.environ.get("INSTANTIMPACT_COMFY_URL", "http://127.0.0.1:8188"),
        os.environ.get("INSTANTIMPACT_DATA_DIR", "(default)"),
        os.environ.get("INSTANTIMPACT_WORKFLOWS_DIR", "(default)"),
        WorkerSettings.job_timeout,
    )
    log.info("weights: %s", _weights_summary())
    pause = os.environ.get("INSTANTIMPACT_GPU_PAUSE_CONTAINERS") or "(none)"
    life = os.environ.get("INSTANTIMPACT_COMFY_LIFECYCLE") or "job"
    log.info("gpu services paused per job: %s", pause)
    log.info("comfy lifecycle=%s (job=stop after stills, keep=unload only)", life)
    run_worker(WorkerSettings)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
