"""Background consumer: Redis job events → SQLite (API is sole DB writer)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.config import get_settings
from app.db.session import get_session_factory
from app.services.jobs import apply_job_event

log = logging.getLogger("instantimpact.job_events")

_task: asyncio.Task[None] | None = None
_stop = asyncio.Event()


async def _consume_loop() -> None:
    settings = get_settings()
    try:
        import redis.asyncio as redis
    except ImportError:
        log.warning("redis package missing — job event consumer disabled")
        return

    r = redis.from_url(settings.redis_url, decode_responses=True)
    log.info("Job event consumer listening on instantimpact:job_events (%s)", settings.redis_url)
    factory = get_session_factory()
    try:
        while not _stop.is_set():
            try:
                # BRPOP with timeout so we can check stop flag
                item = await r.brpop("instantimpact:job_events", timeout=2)
                if not item:
                    continue
                _key, payload = item
                try:
                    event: dict[str, Any] = json.loads(payload)
                except json.JSONDecodeError:
                    log.warning("Invalid job event JSON: %s", payload[:200])
                    continue
                async with factory() as session:
                    try:
                        await apply_job_event(session, event)
                    except Exception:
                        log.exception("Failed applying job event: %s", event)
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
