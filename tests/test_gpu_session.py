from __future__ import annotations

import pytest

from test_gpu_services import FakeContainer, install_fake_docker
from worker.gpu_session import GpuSession


class FakeComfy:
    def __init__(self) -> None:
        self.ensure_calls = 0
        self.stop_calls = 0
        self.unload_calls = 0
        self._healthy = False

    async def healthy(self) -> bool:
        return self._healthy

    async def ensure_running(self) -> bool:
        self.ensure_calls += 1
        started = not self._healthy
        self._healthy = True
        return started

    async def unload(self) -> None:
        self.unload_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1
        self._healthy = False


@pytest.fixture
def fake_comfy(monkeypatch):
    inst = FakeComfy()
    monkeypatch.setattr("worker.gpu_session.ComfyProcess", lambda: inst)
    return inst


@pytest.mark.asyncio
async def test_stills_session_pauses_tenants_then_starts_comfy(monkeypatch, fake_comfy):
    containers = {
        "vllm": FakeContainer("vllm", "running"),
        "ollama": FakeContainer("ollama", "running"),
    }
    install_fake_docker(monkeypatch, containers)
    monkeypatch.setenv("INSTANTIMPACT_GPU_PAUSE_CONTAINERS", "vllm,ollama")
    monkeypatch.setenv("INSTANTIMPACT_COMFY_LIFECYCLE", "job")

    session = GpuSession(kind="stills")
    session.services.names = ["vllm", "ollama"]
    msg = await session.acquire()
    assert "paused" in msg
    assert fake_comfy.ensure_calls == 1
    assert containers["vllm"].status == "exited"

    await session.release()
    assert fake_comfy.stop_calls == 1
    assert containers["vllm"].start_calls == 1
    assert containers["ollama"].start_calls == 1


@pytest.mark.asyncio
async def test_attach_lifecycle_does_not_spawn_or_stop_comfy(monkeypatch, fake_comfy):
    fake_comfy._healthy = True
    install_fake_docker(monkeypatch, {})
    monkeypatch.setenv("INSTANTIMPACT_COMFY_LIFECYCLE", "attach")
    session = GpuSession(kind="stills")
    session.services.names = []
    msg = await session.acquire()
    assert "attached" in msg.lower()
    assert fake_comfy.ensure_calls == 0
    await session.release()
    assert fake_comfy.unload_calls == 1
    assert fake_comfy.stop_calls == 0


@pytest.mark.asyncio
async def test_keep_lifecycle_unloads_comfy_instead_of_stopping(monkeypatch, fake_comfy):
    install_fake_docker(monkeypatch, {})
    monkeypatch.setenv("INSTANTIMPACT_COMFY_LIFECYCLE", "keep")
    session = GpuSession(kind="stills")
    session.services.names = []
    await session.acquire()
    await session.release()
    assert fake_comfy.unload_calls == 1
    assert fake_comfy.stop_calls == 0


@pytest.mark.asyncio
async def test_train_session_stops_comfy_so_toolkit_owns_the_gpu(monkeypatch, fake_comfy):
    fake_comfy._healthy = True
    containers = {"vllm": FakeContainer("vllm", "running")}
    install_fake_docker(monkeypatch, containers)
    session = GpuSession(kind="train")
    session.services.names = ["vllm"]
    msg = await session.acquire()
    assert "stopped Comfy" in msg
    assert fake_comfy.stop_calls == 1
    assert fake_comfy.ensure_calls == 0
    await session.release()
    assert containers["vllm"].start_calls == 1


def test_listen_port_from_url():
    from worker.comfy_process import listen_port

    assert listen_port("http://127.0.0.1:8188") == 8188
    assert listen_port("http://127.0.0.1") == 80
