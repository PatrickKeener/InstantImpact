"""Minimal ComfyUI HTTP client (API mode)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = str(uuid.uuid4())

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/system_stats")
                return r.status_code == 200
        except Exception:
            return False

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        payload = {"prompt": workflow, "client_id": self.client_id}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/prompt", json=payload)
            r.raise_for_status()
            data = r.json()
            return str(data.get("prompt_id") or data.get("node_errors") or "")

    async def get_history(self, prompt_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.base_url}/history/{prompt_id}")
            r.raise_for_status()
            return r.json()

    async def free_memory(self, unload_models: bool = True) -> None:
        """Best-effort VRAM reclaim."""
        payload = {"unload_models": unload_models, "free_memory": True}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(f"{self.base_url}/free", json=payload)
        except Exception:
            pass
