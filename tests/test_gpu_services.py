from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from worker.gpu_services import GpuServiceError, GpuServiceLease, configured_container_names


class FakeContainer:
    def __init__(self, name: str, status: str, health: list[str] | None = None) -> None:
        self.name = name
        self.status = status
        self.stop_calls = 0
        self.start_calls = 0
        self.reload_calls = 0
        # Successive health readings, last value repeating once exhausted.
        self._health = list(health or [])
        self.attrs: dict = {}
        self._apply_health()

    def _apply_health(self) -> None:
        if not self._health:
            self.attrs = {"State": {}}
            return
        value = self._health.pop(0) if len(self._health) > 1 else self._health[0]
        self.attrs = {"State": {"Health": {"Status": value}}}

    def reload(self) -> None:
        self.reload_calls += 1
        self._apply_health()

    def stop(self, timeout: int) -> None:
        assert timeout == 30
        self.stop_calls += 1
        self.status = "exited"

    def start(self) -> None:
        self.start_calls += 1
        self.status = "running"


class FakeClient:
    def __init__(self, containers: dict[str, FakeContainer], not_found: type[Exception]) -> None:
        self._items = containers
        self.containers = SimpleNamespace(get=self.get)
        self._not_found = not_found

    def get(self, name: str) -> FakeContainer:
        if name not in self._items:
            raise self._not_found(name)
        return self._items[name]

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        pass


def install_fake_docker(monkeypatch, containers: dict[str, FakeContainer]) -> None:
    class NotFound(Exception):
        pass

    fake_client = FakeClient(containers, NotFound)
    fake_module = SimpleNamespace(
        from_env=lambda: fake_client,
        errors=SimpleNamespace(NotFound=NotFound),
    )
    monkeypatch.setitem(sys.modules, "docker", fake_module)


def test_configured_container_names_are_trimmed_and_deduplicated(monkeypatch):
    monkeypatch.setenv(
        "INSTANTIMPACT_GPU_PAUSE_CONTAINERS",
        " ollama, nemotron-ocr-nim,ollama,,vllm ",
    )
    assert configured_container_names() == ["ollama", "nemotron-ocr-nim", "vllm"]


@pytest.mark.asyncio
async def test_lease_stops_only_running_services(monkeypatch):
    containers = {
        "ollama": FakeContainer("ollama", "running"),
        "nemotron-ocr-nim": FakeContainer("nemotron-ocr-nim", "exited"),
        "vllm": FakeContainer("vllm", "running"),
    }
    install_fake_docker(monkeypatch, containers)
    lease = GpuServiceLease(names=list(containers))

    assert await lease.acquire() == ["ollama", "vllm"]
    assert containers["ollama"].status == "exited"
    assert containers["vllm"].status == "exited"
    assert containers["nemotron-ocr-nim"].stop_calls == 0


@pytest.mark.asyncio
async def test_restore_brings_up_every_configured_service(monkeypatch):
    # nemotron was stopped by hand before the job; the configured list is the
    # idle state, so it still comes back.
    containers = {
        "ollama": FakeContainer("ollama", "running"),
        "nemotron-ocr-nim": FakeContainer("nemotron-ocr-nim", "exited"),
    }
    install_fake_docker(monkeypatch, containers)
    lease = GpuServiceLease(names=list(containers))

    assert await lease.acquire() == ["ollama"]
    assert await lease.restore() == ["ollama", "nemotron-ocr-nim"]
    assert containers["ollama"].start_calls == 1
    assert containers["nemotron-ocr-nim"].start_calls == 1


@pytest.mark.asyncio
async def test_restore_leaves_an_already_running_service_alone(monkeypatch):
    containers = {"ollama": FakeContainer("ollama", "running")}
    install_fake_docker(monkeypatch, containers)
    lease = GpuServiceLease(names=["ollama"])

    assert await lease.restore() == []
    assert containers["ollama"].start_calls == 0


@pytest.mark.asyncio
async def test_missing_configured_container_is_ignored(monkeypatch):
    containers = {"ollama": FakeContainer("ollama", "running")}
    install_fake_docker(monkeypatch, containers)
    lease = GpuServiceLease(names=["ollama", "not-installed"])

    assert await lease.acquire() == ["ollama"]
    assert await lease.restore() == ["ollama"]


@pytest.mark.asyncio
async def test_stop_waits_for_a_starting_service(monkeypatch):
    # An NVIDIA NIM reports running while it is still building its workspace;
    # stopping it there corrupts the workspace.
    nim = FakeContainer("nemotron-ocr-nim", "running", health=["starting", "starting", "healthy"])
    install_fake_docker(monkeypatch, {"nemotron-ocr-nim": nim})
    monkeypatch.setattr("worker.gpu_services.time.sleep", lambda _s: None)
    lease = GpuServiceLease(names=["nemotron-ocr-nim"], health_timeout=60.0)

    assert await lease.acquire() == ["nemotron-ocr-nim"]
    assert nim.reload_calls > 1
    assert nim.stop_calls == 1


@pytest.mark.asyncio
async def test_stop_gives_up_waiting_after_the_timeout(monkeypatch):
    nim = FakeContainer("nemotron-ocr-nim", "running", health=["starting"])
    install_fake_docker(monkeypatch, {"nemotron-ocr-nim": nim})
    monkeypatch.setattr("worker.gpu_services.time.sleep", lambda _s: None)
    lease = GpuServiceLease(names=["nemotron-ocr-nim"], health_timeout=0.05)

    assert await lease.acquire() == ["nemotron-ocr-nim"]
    assert nim.stop_calls == 1


@pytest.mark.asyncio
async def test_healthy_service_is_stopped_without_waiting(monkeypatch):
    ollama = FakeContainer("ollama", "running", health=["healthy"])
    install_fake_docker(monkeypatch, {"ollama": ollama})
    lease = GpuServiceLease(names=["ollama"], health_timeout=60.0)

    assert await lease.acquire() == ["ollama"]
    assert ollama.reload_calls == 1
    assert ollama.stop_calls == 1


@pytest.mark.asyncio
async def test_disabled_lease_is_a_no_op(monkeypatch):
    install_fake_docker(monkeypatch, {})
    lease = GpuServiceLease(names=[])

    assert lease.enabled is False
    assert await lease.acquire() == []
    assert await lease.restore() == []


@pytest.mark.asyncio
async def test_requested_orchestration_fails_closed_without_docker(monkeypatch):
    fake_module = SimpleNamespace(from_env=lambda: (_ for _ in ()).throw(RuntimeError("no socket")))
    monkeypatch.setitem(sys.modules, "docker", fake_module)
    lease = GpuServiceLease(names=["ollama"])

    with pytest.raises(GpuServiceError, match="mount /var/run/docker.sock"):
        await lease.acquire()
