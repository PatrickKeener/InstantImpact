"""Start and stop the native ComfyUI process for per-job GPU handoff."""

from __future__ import annotations

import logging
import os
import shlex
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger("instantimpact.worker.comfy")


def comfy_url() -> str:
    return (os.environ.get("INSTANTIMPACT_COMFY_URL") or "http://127.0.0.1:8188").rstrip("/")


def comfy_lifecycle() -> str:
    raw = (os.environ.get("INSTANTIMPACT_COMFY_LIFECYCLE") or "job").strip().lower()
    return raw if raw in {"job", "keep"} else "job"


def start_timeout_seconds() -> float:
    raw = (os.environ.get("INSTANTIMPACT_COMFY_START_TIMEOUT") or "").strip()
    try:
        return max(15.0, float(raw)) if raw else 90.0
    except ValueError:
        return 90.0


def repo_root() -> Path:
    env = os.environ.get("INSTANTIMPACT_RUN_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def pid_path() -> Path:
    path = repo_root() / ".run" / "pids" / "comfy.pid"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    path = repo_root() / ".run" / "logs" / "comfy.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def listen_port(url: str | None = None) -> int:
    parsed = urlparse(url or comfy_url())
    if parsed.port:
        return int(parsed.port)
    return 443 if parsed.scheme == "https" else 80


def listen_host(url: str | None = None) -> str:
    parsed = urlparse(url or comfy_url())
    return parsed.hostname or "127.0.0.1"


class ComfyProcessError(RuntimeError):
    pass


class ComfyProcess:
    """Ensure Comfy is up for stills, then fully release the GPU afterward."""

    def __init__(self) -> None:
        self.started_this_session = False

    async def healthy(self) -> bool:
        from instantimpact_comfy.client import ComfyClient

        return await ComfyClient(comfy_url(), timeout=5.0).health()

    async def ensure_running(self) -> bool:
        """Start Comfy if it is down. Returns True when this call spawned it."""
        if await self.healthy():
            log.info("Comfy already healthy at %s", comfy_url())
            return False
        self._spawn()
        self.started_this_session = True
        await self._wait_healthy()
        return True

    async def unload(self) -> None:
        from instantimpact_comfy.client import ComfyClient

        try:
            await ComfyClient(comfy_url(), timeout=30.0).free_memory(unload_models=True)
        except Exception:
            log.exception("Comfy /free failed")

    async def stop(self) -> None:
        """Unload, then kill the Comfy process so CUDA is actually released."""
        if await self.healthy():
            await self.unload()
        self._kill_tracked()
        if await self.healthy():
            self._kill_port_listeners()
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if not await self.healthy():
                pid_path().unlink(missing_ok=True)
                log.info("Comfy stopped")
                return
            time.sleep(0.4)
        log.warning("Comfy still answering %s after stop", comfy_url())

    def _spawn(self) -> None:
        from instantimpact_common.flux_inventory import resolve_comfy_root

        comfy_dir = resolve_comfy_root(os.environ.get("INSTANTIMPACT_COMFY_DIR"))
        if comfy_dir is None:
            raise ComfyProcessError(
                "ComfyUI not found. Set INSTANTIMPACT_COMFY_DIR to the directory that contains main.py."
            )
        python = _comfy_python(comfy_dir)
        host = listen_host()
        port = listen_port()
        inner = (
            f"cd {shlex.quote(str(comfy_dir))} && exec {shlex.quote(str(python))} "
            f"main.py --listen {shlex.quote(host)} --port {port}"
        )
        user = _drop_to_owner(comfy_dir)
        if user:
            cmd = ["sudo", "-u", user, "-H", "bash", "-c", inner]
            log.info("starting Comfy as %s in %s", user, comfy_dir)
        else:
            cmd = ["bash", "-c", inner]
            log.info("starting Comfy in %s", comfy_dir)
        handle = log_path().open("ab")
        proc = subprocess.Popen(
            cmd,
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        pid_path().write_text(str(proc.pid), encoding="utf-8")

    async def _wait_healthy(self) -> None:
        import asyncio

        timeout = start_timeout_seconds()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await self.healthy():
                log.info("Comfy healthy at %s", comfy_url())
                return
            await asyncio.sleep(1.0)
        raise ComfyProcessError(
            f"Comfy did not become healthy at {comfy_url()} within {timeout:.0f}s. "
            f"See {log_path()}"
        )

    def _kill_tracked(self) -> None:
        path = pid_path()
        if not path.is_file():
            return
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
        except ValueError:
            path.unlink(missing_ok=True)
            return
        _kill_pid(pid)
        path.unlink(missing_ok=True)

    def _kill_port_listeners(self) -> None:
        port = listen_port()
        if os.name == "nt":
            return
        try:
            subprocess.run(
                ["fuser", "-k", f"{port}/tcp"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            log.info("sent fuser -k %s/tcp", port)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            log.warning("could not fuser Comfy port %s", port)


def _comfy_python(comfy_dir: Path) -> Path:
    for rel in (".venv/bin/python", "venv/bin/python", ".venv/Scripts/python.exe"):
        candidate = comfy_dir / rel
        if candidate.is_file():
            return candidate
    return Path("python3")


def _drop_to_owner(comfy_dir: Path) -> str | None:
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return None
    try:
        import pwd

        owner = pwd.getpwuid(comfy_dir.stat().st_uid).pw_name
    except Exception:
        return None
    if owner and owner != "root":
        return owner
    return None


def _kill_pid(pid: int) -> None:
    if pid <= 0:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.2)
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
