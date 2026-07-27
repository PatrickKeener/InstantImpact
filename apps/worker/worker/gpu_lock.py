"""Redis GPU mutex with heartbeat."""

from __future__ import annotations

import asyncio
import time
from typing import Any


class GpuLock:
    KEY = "instantimpact:gpu"

    def __init__(self, redis: Any, holder_id: str, ttl_seconds: int = 120) -> None:
        self.redis = redis
        self.holder_id = holder_id
        self.ttl = ttl_seconds
        self._heartbeat_task: asyncio.Task | None = None

    async def acquire(self, timeout: float = 3600.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            ok = await self.redis.set(self.KEY, self.holder_id, nx=True, ex=self.ttl)
            if ok:
                self._heartbeat_task = asyncio.create_task(self._heartbeat())
                return True
            await asyncio.sleep(1.0)
        return False

    async def _heartbeat(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.ttl / 3)
                val = await self.redis.get(self.KEY)
                if val and val.decode() == self.holder_id:
                    await self.redis.expire(self.KEY, self.ttl)
                else:
                    break
        except asyncio.CancelledError:
            return

    async def release(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        val = await self.redis.get(self.KEY)
        if val and val.decode() == self.holder_id:
            await self.redis.delete(self.KEY)


async def is_cancel_requested(redis: Any, job_id: str) -> bool:
    return bool(await redis.exists(f"instantimpact:cancel:{job_id}"))
