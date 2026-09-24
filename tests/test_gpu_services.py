from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from worker.gpu_services import GpuServiceError, GpuServiceLease, configured_container_names


class FakeContainer:
    def __init__(self, name: str, status: str) -> None:
        self.name = name
        self.status = status
        self.stop_calls = 0
        self.start_calls = 0

    def reload(self) -> None:
        pass

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
async def test_lease_restores_only_containers_that_were_running(monkeypatch):
    containers = {
        "ollama": FakeContainer("ollama", "running"),
        "nemotron-ocr-nim": FakeContainer("nemotron-ocr-nim", "exited"),
        "vllm": FakeContainer("vllm", "running"),
    }
    install_fake_docker(monkeypatch, containers)
    lease = GpuServiceLease(names=list(containers))

    assert await lease.acquire() == ["ollama", "vllm"]
    assert containers["ollama"].status == "exited"
    assert containers["nemotron-ocr-nim"].stop_calls == 0
    assert containers["vllm"].status == "exited"

    assert await lease.restore() == ["ollama", "vllm"]
    assert containers["ollama"].start_calls == 1
    assert containers["nemotron-ocr-nim"].start_calls == 0
    assert containers["vllm"].start_calls == 1


@pytest.mark.asyncio
async def test_missing_configured_container_is_ignored(monkeypatch):
    containers = {"ollama": FakeContainer("ollama", "running")}
    install_fake_docker(monkeypatch, containers)
    lease = GpuServiceLease(names=["ollama", "not-installed"])

    assert await lease.acquire() == ["ollama"]
    assert await lease.restore() == ["ollama"]


@pytest.mark.asyncio
async def test_requested_orchestration_fails_closed_without_docker(monkeypatch):
    fake_module = SimpleNamespace(from_env=lambda: (_ for _ in ()).throw(RuntimeError("no socket")))
    monkeypatch.setitem(sys.modules, "docker", fake_module)
    lease = GpuServiceLease(names=["ollama"])

    with pytest.raises(GpuServiceError, match="mount /var/run/docker.sock"):
        await lease.acquire()
