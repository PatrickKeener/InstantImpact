"""ARQ worker entrypoint.

python -m worker.main
"""

from __future__ import annotations

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


async def run_generation_job(ctx, job_id: str, request_path: str, job_type: str):
    if job_type == "lora_train":
        return await process_lora_train(ctx, job_id, request_path)
    return await process_still_job(ctx, job_id, request_path, job_type)


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


def main() -> None:
    from arq.worker import run_worker

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
    run_worker(WorkerSettings)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
