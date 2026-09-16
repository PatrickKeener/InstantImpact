"""Background consumer: Redis job events → SQLite (API is sole DB writer).

Durable ACK: BRPOPLPUSH onto a processing list, LREM after a successful apply.
On startup, replay anything left in the processing list (apply is idempotent).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.config import get_settings
from app.db.session import get_session_factory
from app.services.jobs import apply_job_event

log = logging.getLogger("instantimpact.job_events")

QUEUE = "instantimpact:job_events"
PROCESSING = "instantimpact:job_events:processing"
DEAD = "instantimpact:job_events:dead"

_task: asyncio.Task[None] | None = None
_stop = asyncio.Event()


async def _apply_payload(factory, payload: str) -> None:
    try:
        event: dict[str, Any] = json.loads(payload)
    except json.JSONDecodeError:
        log.warning("Invalid job event JSON: %s", payload[:200])
        return
    async with factory() as session:
        await apply_job_event(session, event)


async def _replay_processing(r, factory) -> None:
    items = await r.lrange(PROCESSING, 0, -1)
    for payload in items:
        try:
            await _apply_payload(factory, payload)
            await r.lrem(PROCESSING, 1, payload)
        except Exception:
            log.exception("Failed replaying in-flight job event")
            await r.lpush(DEAD, payload)
            await r.lrem(PROCESSING, 1, payload)


async def _consume_loop() -> None:
    settings = get_settings()
    try:
        import redis.asyncio as redis
    except ImportError:
        log.warning("redis package missing — job event consumer disabled")
        return

    r = redis.from_url(settings.redis_url, decode_responses=True)
    log.info("Job event consumer listening on %s (%s)", QUEUE, settings.redis_url)
    factory = get_session_factory()
    try:
        try:
            await _replay_processing(r, factory)
        except Exception:
            log.exception("Could not replay processing list (Redis down?)")
        while not _stop.is_set():
            try:
                payload = await r.brpoplpush(QUEUE, PROCESSING, timeout=2)
                if not payload:
                    continue
                try:
                    await _apply_payload(factory, payload)
                    await r.lrem(PROCESSING, 1, payload)
                except Exception:
                    log.exception("Failed applying job event")
                    await r.lpush(DEAD, payload)
                    await r.lrem(PROCESSING, 1, payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Job event consumer loop error")
                await asyncio.sleep(1.0)
    finally:
        await r.aclose()


def start_job_event_consumer() -> None:
    global _task
    _stop.clear()
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_consume_loop(), name="job_event_consumer")


async def stop_job_event_consumer() -> None:
    global _task
    _stop.set()
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
