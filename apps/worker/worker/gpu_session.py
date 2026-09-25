"""Per-job GPU handoff: pause vLLM/Ollama, run Comfy or train, then restore."""

from __future__ import annotations

import logging

from worker.comfy_process import ComfyProcess, ComfyProcessError, comfy_lifecycle
from worker.gpu_services import GpuServiceError, GpuServiceLease

log = logging.getLogger("instantimpact.worker.gpu_session")


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
        return "GPU acquired" + (f" ({'; '.join(self.notes)})" if self.notes else "")

    async def release(self) -> None:
        """Always free Comfy VRAM before bringing vLLM/Ollama back."""
        try:
            if self.kind == "stills":
                if comfy_lifecycle() in {"keep", "attach"}:
                    await self.comfy.unload()
                else:
                    await self.comfy.stop()
            elif await self.comfy.healthy() and comfy_lifecycle() != "attach":
                await self.comfy.stop()
        except Exception:
            log.exception("failed to release Comfy")
        restored = await self.services.restore()
        if restored:
            log.info("restored GPU services: %s", ", ".join(restored))
