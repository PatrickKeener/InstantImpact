"""Pause competing Docker GPU services for the duration of an InstantImpact job."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("instantimpact.worker.gpu_services")


class GpuServiceError(RuntimeError):
    pass


def configured_container_names() -> list[str]:
    raw = os.environ.get("INSTANTIMPACT_GPU_PAUSE_CONTAINERS", "")
    return list(dict.fromkeys(name.strip() for name in raw.split(",") if name.strip()))


@dataclass
class GpuServiceLease:
    """Pause configured containers for a job, then bring them all back.

    The configured list describes what should be running whenever the GPU is
    idle, so restore starts every name in it — including one an operator had
    stopped by hand before the job.
    """

    names: list[str] = field(default_factory=configured_container_names)
    stopped: list[str] = field(default_factory=list)

    @property
    def enabled(self) -> bool:
        return bool(self.names)

    async def acquire(self) -> list[str]:
        if not self.enabled:
            return []
        try:
            return await asyncio.to_thread(self._stop_running)
        except Exception as exc:
            # If one stop failed, do not leave containers stopped after a
            # partially acquired lease.
            await self.restore()
            if isinstance(exc, GpuServiceError):
                raise
            raise GpuServiceError(f"Could not pause GPU services: {exc}") from exc

    def _stop_running(self) -> list[str]:
        try:
            import docker
        except ImportError as exc:
            raise GpuServiceError("Docker SDK is not installed in the worker") from exc

        try:
            client = docker.from_env()
            client.ping()
        except Exception as exc:
            raise GpuServiceError(
                "Docker is unavailable; mount /var/run/docker.sock into the worker"
            ) from exc

        try:
            for name in self.names:
                try:
                    container = client.containers.get(name)
                except docker.errors.NotFound:
                    log.warning("configured GPU service does not exist: %s", name)
                    continue
                container.reload()
                if container.status != "running":
                    log.info("GPU service already stopped; leaving it stopped: %s", name)
                    continue
                log.info("pausing GPU service: %s", name)
                container.stop(timeout=30)
                self.stopped.append(name)
            return list(self.stopped)
        finally:
            client.close()

    async def restore(self) -> list[str]:
        if not self.enabled:
            return []
        self.stopped.clear()
        try:
            return await asyncio.to_thread(self._start, list(self.names))
        except Exception:
            # Restoration is best effort, but it must be loud: the generation
            # result should not be hidden just because an unrelated service
            # failed to restart.
            log.exception("failed to restore one or more GPU services: %s", self.names)
            return []

    @staticmethod
    def _start(names: list[str]) -> list[str]:
        import docker

        client = docker.from_env()
        restored: list[str] = []
        try:
            for name in names:
                try:
                    container = client.containers.get(name)
                    container.reload()
                    if container.status == "running":
                        continue
                    log.info("restoring GPU service: %s", name)
                    container.start()
                    restored.append(name)
                except Exception:
                    log.exception("could not restore GPU service: %s", name)
            return restored
        finally:
            client.close()
