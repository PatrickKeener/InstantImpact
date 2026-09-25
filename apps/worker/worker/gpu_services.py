"""Pause competing Docker GPU services for the duration of an InstantImpact job."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("instantimpact.worker.gpu_services")

_HEALTH_POLL_SECONDS = 2.0


class GpuServiceError(RuntimeError):
    pass


def configured_container_names() -> list[str]:
    raw = os.environ.get("INSTANTIMPACT_GPU_PAUSE_CONTAINERS", "")
    return list(dict.fromkeys(name.strip() for name in raw.split(",") if name.strip()))


def health_timeout_seconds() -> float:
    raw = (os.environ.get("INSTANTIMPACT_GPU_PAUSE_HEALTH_TIMEOUT") or "").strip()
    try:
        return max(0.0, float(raw)) if raw else 120.0
    except ValueError:
        return 120.0


def _health_status(container: Any) -> str | None:
    state = (getattr(container, "attrs", None) or {}).get("State") or {}
    return (state.get("Health") or {}).get("Status")


@dataclass
class GpuServiceLease:
    """Pause configured containers for a job, then bring them all back.

    The configured list describes what should be running whenever the GPU is
    idle, so restore starts every name in it — including one an operator had
    stopped by hand before the job.
    """

    names: list[str] = field(default_factory=configured_container_names)
    stopped: list[str] = field(default_factory=list)
    health_timeout: float = field(default_factory=health_timeout_seconds)

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
                self._await_ready(container, name)
                log.info("pausing GPU service: %s", name)
                container.stop(timeout=30)
                self.stopped.append(name)
            return list(self.stopped)
        finally:
            client.close()

    def _await_ready(self, container: Any, name: str) -> None:
        """Let a still-initializing service finish before stopping it.

        Docker reports a container as running long before a slow starter is
        usable — an NVIDIA NIM spends minutes laying out its model workspace —
        and stopping partway through that leaves the workspace corrupt.
        """
        if self.health_timeout <= 0 or _health_status(container) != "starting":
            return
        log.info("waiting up to %ss for %s to finish starting", self.health_timeout, name)
        deadline = time.monotonic() + self.health_timeout
        while time.monotonic() < deadline:
            time.sleep(_HEALTH_POLL_SECONDS)
            container.reload()
            if container.status != "running":
                return
            status = _health_status(container)
            if status != "starting":
                log.info("%s finished starting (health=%s)", name, status)
                return
        log.warning("%s still starting after %ss; pausing it anyway", name, self.health_timeout)

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
