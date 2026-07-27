"""Still generation task — loads work from FS request.json only."""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from typing import Any

from worker.gpu_lock import GpuLock, is_cancel_requested


async def process_still_job(
    ctx: dict[str, Any],
    job_id: str,
    request_path: str,
    job_type: str,
) -> dict[str, Any]:
    """
    Worker entry. Does NOT open SQLite.
    Publishes results to Redis list for API consumer (or completes mock inline for MVP).
    """
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
    acquired = await lock.acquire(timeout=10.0)
    if not acquired:
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "gpu_busy",
                "message": "Could not acquire GPU lock",
            },
        )
        return {"ok": False}

    try:
        await _publish(redis, {"job_id": job_id, "event": "running", "message": "GPU acquired"})
        if snapshot.get("mock", True):
            result = await _run_mock(redis, snapshot)
        else:
            # Real Comfy path — binder + client (requires Comfy running)
            result = await _run_comfy(redis, snapshot)
        return result
    finally:
        await lock.release()


async def _run_mock(redis: Any, snapshot: dict) -> dict:
    # Signal API to run mock completion via result bus event 'run_mock'
    # For simplicity, publish completed with note; API mock path is primary when Redis down.
    job_id = snapshot["job_id"]
    items = snapshot.get("items") or []
    for item in items:
        if await is_cancel_requested(redis, job_id):
            await _publish(redis, {"job_id": job_id, "event": "cancelled"})
            return {"ok": False, "cancelled": True}
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "item_done",
                "item_index": item.get("item_index"),
                "message": "mock item (API may complete assets)",
            },
        )
    await _publish(
        redis,
        {
            "job_id": job_id,
            "event": "completed",
            "message": "worker mock pass — ensure API mock runner applied assets",
        },
    )
    return {"ok": True}


async def _run_comfy(redis: Any, snapshot: dict) -> dict:
    await _publish(
        redis,
        {
            "job_id": snapshot["job_id"],
            "event": "failed",
            "error_code": "comfy_not_wired",
            "message": "Real Comfy still path lands in PR-07; enable mock or implement binder submit",
        },
    )
    return {"ok": False}


async def _publish(redis: Any, event: dict) -> None:
    payload = json.dumps(event)
    await redis.rpush("instantimpact:job_events", payload)
    await redis.publish("instantimpact:job_events", payload)
