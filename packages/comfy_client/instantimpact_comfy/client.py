"""Minimal ComfyUI HTTP client (API mode)."""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import httpx

from instantimpact_common.offline import enforce_strict_offline


class ComfyClientError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout: float = 300.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = str(uuid.uuid4())
        strict = os.environ.get("INSTANTIMPACT_STRICT_OFFLINE", "").lower() in {"1", "true", "yes"}
        enforce_strict_offline(self.base_url, strict)

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/system_stats")
                return r.status_code == 200
        except Exception:
            return False

    async def object_info(self) -> dict[str, Any] | None:
        """Node class inventory. None if Comfy is too old or unreachable."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(f"{self.base_url}/object_info")
                if r.status_code != 200:
                    return None
                data = r.json()
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        """Submit an API-format prompt graph. Returns prompt_id."""
        # Comfy only accepts node id keys; drop metadata
        prompt = {
            k: v
            for k, v in workflow.items()
            if isinstance(v, dict) and "class_type" in v
        }
        payload = {"prompt": prompt, "client_id": self.client_id}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/prompt", json=payload)
            if r.status_code >= 400:
                detail = r.text
                try:
                    detail = r.json()
                except Exception:
                    pass
                raise ComfyClientError(f"Comfy /prompt failed ({r.status_code}): {detail}")
            data = r.json()
            if data.get("node_errors"):
                raise ComfyClientError(f"Comfy node_errors: {data['node_errors']}")
            prompt_id = data.get("prompt_id")
            if not prompt_id:
                raise ComfyClientError(f"Comfy response missing prompt_id: {data}")
            return str(prompt_id)

    async def get_history(self, prompt_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.base_url}/history/{prompt_id}")
            r.raise_for_status()
            return r.json()

    @staticmethod
    def error_from_history(entry: dict[str, Any]) -> str | None:
        """Extract Comfy's execution error from a history entry.

        Comfy accepts a prompt over HTTP and only reports runtime failures here,
        in status.messages, so a failed prompt is otherwise indistinguishable
        from one that simply produced no images.
        """
        status = entry.get("status") or {}
        details: list[str] = []
        for message in status.get("messages") or []:
            if not (isinstance(message, (list, tuple)) and len(message) == 2):
                continue
            event, data = message
            if event not in {"execution_error", "execution_interrupted"}:
                continue
            if not isinstance(data, dict):
                details.append(f"{event}: {data}")
                continue
            node = data.get("node_type") or data.get("node_id")
            reason = (
                data.get("exception_message") or data.get("exception_type") or str(event)
            )
            details.append(f"{node}: {reason}" if node else str(reason))
        if details:
            return "; ".join(details)
        if status.get("status_str") == "error":
            return "Comfy reported status_str=error without a message"
        return None

    @staticmethod
    def _is_complete(entry: dict[str, Any]) -> bool:
        status = entry.get("status")
        if isinstance(status, dict) and "completed" in status:
            return bool(status["completed"])
        # Older Comfy builds only write history once a prompt finishes.
        return True

    async def wait_for_prompt(
        self,
        prompt_id: str,
        *,
        poll_interval: float = 0.5,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Poll history until the prompt finishes. Returns the history entry.

        Comfy publishes a history entry as soon as a prompt starts, so presence
        alone does not mean it is done; returning early yields an entry with no
        outputs and hides whatever actually went wrong.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (timeout or self.timeout)
        entry: dict[str, Any] | None = None
        while True:
            history = await self.get_history(prompt_id)
            entry = history.get(prompt_id)
            if entry is not None:
                error = self.error_from_history(entry)
                if error:
                    raise ComfyClientError(f"Comfy prompt {prompt_id} failed — {error}")
                if self._is_complete(entry):
                    return entry
            if loop.time() >= deadline:
                state = (entry or {}).get("status") or "not queued"
                raise ComfyClientError(
                    f"Timed out waiting for Comfy prompt {prompt_id} (status: {state})"
                )
            await asyncio.sleep(poll_interval)

    async def get_image(
        self,
        *,
        filename: str,
        subfolder: str = "",
        folder_type: str = "output",
    ) -> bytes:
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.base_url}/view", params=params)
            r.raise_for_status()
            return r.content

    @staticmethod
    def images_from_history(entry: dict[str, Any]) -> list[dict[str, str]]:
        """Extract SaveImage (and similar) outputs from a history entry."""
        images: list[dict[str, str]] = []
        outputs = entry.get("outputs") or {}
        for _node_id, node_out in outputs.items():
            for img in node_out.get("images") or []:
                if isinstance(img, dict) and img.get("filename"):
                    images.append(
                        {
                            "filename": str(img["filename"]),
                            "subfolder": str(img.get("subfolder") or ""),
                            "type": str(img.get("type") or "output"),
                        }
                    )
        return images

    async def upload_image(
        self, data: bytes, filename: str, *, overwrite: bool = True
    ) -> str:
        """Upload a still into Comfy's input folder. Returns the LoadImage filename."""
        files = {"image": (filename, data, "image/png")}
        form = {"overwrite": "true" if overwrite else "false", "type": "input"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{self.base_url}/upload/image", files=files, data=form)
            if r.status_code >= 400:
                raise ComfyClientError(f"Comfy /upload/image failed ({r.status_code}): {r.text}")
            payload = r.json()
        name = str(payload.get("name") or filename)
        subfolder = str(payload.get("subfolder") or "").strip().strip("/")
        return f"{subfolder}/{name}" if subfolder else name

    async def free_memory(self, unload_models: bool = True) -> None:
        """Best-effort VRAM reclaim."""
        payload = {"unload_models": unload_models, "free_memory": True}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(f"{self.base_url}/free", json=payload)
        except Exception:
            pass
