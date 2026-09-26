"""Per-job GPU handoff: pause vLLM/Ollama, run Comfy or train, then restore.

Stills can keep Comfy (and the paused GPU tenants) for
INSTANTIMPACT_COMFY_IDLE_GRACE seconds so a second seed set does not pay
Comfy startup again. A new job cancels that timer. Train tears down immediately.
"""

from __future__ import annotations

import asyncio
import logging
import os

from worker.comfy_process import ComfyProcess, ComfyProcessError, comfy_lifecycle
from worker.gpu_services import GpuServiceError, GpuServiceLease

log = logging.getLogger("instantimpact.worker.gpu_session")

_hold_lock = asyncio.Lock()
_hold_gen = 0
_hold_active = False
_teardown_task: asyncio.Task[None] | None = None


def idle_grace_seconds() -> float:
    raw = (os.environ.get("INSTANTIMPACT_COMFY_IDLE_GRACE") or "").strip()
    try:
        return max(0.0, float(raw)) if raw else 0.0
    except ValueError:
        return 0.0


async def reset_hold_for_tests() -> None:
    """Drop in-memory hold state without touching Docker/Comfy."""
    global _hold_active, _hold_gen, _teardown_task
    task = _teardown_task
    _teardown_task = None
    _hold_active = False
    _hold_gen = 0
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def teardown_gpu_hold() -> None:
    """Stop Comfy and restore vLLM/Ollama if a grace hold is outstanding."""
    global _teardown_task, _hold_active, _hold_gen
    async with _hold_lock:
        _hold_gen += 1
        task = _teardown_task
        _teardown_task = None
        if task:
            task.cancel()
        if _hold_active:
            await _run_teardown()
            _hold_active = False


async def _run_teardown() -> None:
    comfy = ComfyProcess()
    life = comfy_lifecycle()
    try:
        if life in {"keep", "attach"}:
            await comfy.unload()
        else:
            await comfy.stop()
    except Exception:
        log.exception("failed to release Comfy")
    restored = await GpuServiceLease().restore()
    if restored:
        log.info("restored GPU services: %s", ", ".join(restored))


async def _delayed_teardown(expected_gen: int, delay: float) -> None:
    global _hold_active, _teardown_task
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    async with _hold_lock:
        if expected_gen != _hold_gen:
            return
        log.info("idle grace (%.0fs) expired — stopping Comfy, restoring vLLM/Ollama", delay)
        await _run_teardown()
        _hold_active = False
        _teardown_task = None


class GpuSession:
    """Idle GPU tenants own the card. InstantImpact borrows it for one job."""

    def __init__(self, kind: str = "stills") -> None:
        if kind not in {"stills", "train"}:
            raise ValueError(f"unknown GPU session kind {kind!r}")
        self.kind = kind
        self.services = GpuServiceLease()
        self.comfy = ComfyProcess()
        self.notes: list[str] = []

    async def acquire(self) -> str:
        global _hold_gen, _hold_active, _teardown_task
        async with _hold_lock:
            _hold_gen += 1
            task = _teardown_task
            _teardown_task = None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if self.kind == "stills" and _hold_active and await self.comfy.healthy():
            self.notes.append("kept GPU from idle grace")
            log.info("reusing Comfy held from idle grace")
            return "GPU acquired" + (f" ({'; '.join(self.notes)})" if self.notes else "")

        if self.kind == "train" and _hold_active:
            # Toolkit needs the card; drop Comfy now, leave tenants paused.
            try:
                if comfy_lifecycle() == "attach":
                    await self.comfy.unload()
                elif await self.comfy.healthy():
                    await self.comfy.stop()
                    self.notes.append("stopped Comfy held from idle grace")
            except Exception:
                log.exception("failed to drop Comfy before train")
            _hold_active = False

        paused = await self.services.acquire()
        if paused:
            self.notes.append("paused " + ", ".join(paused))
        try:
            life = comfy_lifecycle()
            if self.kind == "stills":
                if life == "attach":
                    if not await self.comfy.healthy():
                        raise ComfyProcessError(
                            "ComfyUI is not running at INSTANTIMPACT_COMFY_URL. "
                            "Start it on the host (this worker will not spawn it)."
                        )
                    self.notes.append("Comfy attached")
                else:
                    started = await self.comfy.ensure_running()
                    if started:
                        self.notes.append("started Comfy")
                    else:
                        self.notes.append("Comfy already up")
            else:
                if await self.comfy.healthy():
                    if life == "attach":
                        await self.comfy.unload()
                        self.notes.append("unloaded Comfy for LoRA train")
                    else:
                        await self.comfy.stop()
                        self.notes.append("stopped Comfy for LoRA train")
        except ComfyProcessError as exc:
            await self.services.restore()
            raise GpuServiceError(str(exc)) from exc
        except Exception:
            await self.services.restore()
            raise
        if self.kind == "stills":
            _hold_active = True
        return "GPU acquired" + (f" ({'; '.join(self.notes)})" if self.notes else "")

    async def release(self) -> None:
        """Free the GPU, or keep Comfy for INSTANTIMPACT_COMFY_IDLE_GRACE seconds."""
        global _teardown_task, _hold_active, _hold_gen
        life = comfy_lifecycle()
        grace = idle_grace_seconds()
        if self.kind == "stills" and life == "job" and grace > 0 and _hold_active:
            async with _hold_lock:
                gen = _hold_gen
                if _teardown_task:
                    _teardown_task.cancel()
                _teardown_task = asyncio.create_task(
                    _delayed_teardown(gen, grace),
                    name="comfy-idle-grace",
                )
            log.info("holding Comfy for %.0fs idle grace (next seed set can reuse it)", grace)
            return

        try:
            if self.kind == "stills":
                if life in {"keep", "attach"}:
                    await self.comfy.unload()
                else:
                    await self.comfy.stop()
            elif await self.comfy.healthy() and life != "attach":
                await self.comfy.stop()
        except Exception:
            log.exception("failed to release Comfy")
        restored = await self.services.restore()
        if restored:
            log.info("restored GPU services: %s", ", ".join(restored))
        _hold_active = False
