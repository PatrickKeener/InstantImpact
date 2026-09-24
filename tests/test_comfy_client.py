"""ComfyUI history handling — a running prompt must not read as a finished one."""

from __future__ import annotations

import pytest

from instantimpact_comfy.client import ComfyClient, ComfyClientError


def test_error_from_history_reports_the_failing_node():
    entry = {
        "status": {
            "status_str": "error",
            "completed": False,
            "messages": [
                ["execution_start", {"prompt_id": "abc"}],
                [
                    "execution_error",
                    {
                        "node_id": "4",
                        "node_type": "CheckpointLoaderSimple",
                        "exception_type": "FileNotFoundError",
                        "exception_message": "flux1-dev.safetensors not found",
                    },
                ],
            ],
        }
    }
    assert ComfyClient.error_from_history(entry) == (
        "CheckpointLoaderSimple: flux1-dev.safetensors not found"
    )


def test_error_from_history_ignores_a_healthy_entry():
    entry = {"status": {"status_str": "success", "completed": True}, "outputs": {}}
    assert ComfyClient.error_from_history(entry) is None


@pytest.mark.asyncio
async def test_wait_for_prompt_keeps_polling_while_incomplete(monkeypatch):
    responses = [
        {},
        {"p1": {"status": {"completed": False, "messages": []}}},
        {"p1": {"status": {"completed": True}, "outputs": {"9": {"images": [{}]}}}},
    ]
    client = ComfyClient("http://127.0.0.1:8188", timeout=5.0)

    async def fake_history(prompt_id: str):
        return responses.pop(0)

    monkeypatch.setattr(client, "get_history", fake_history)
    entry = await client.wait_for_prompt("p1", poll_interval=0.0)
    assert entry["outputs"]["9"]["images"]
    assert not responses


@pytest.mark.asyncio
async def test_wait_for_prompt_raises_comfy_error_detail(monkeypatch):
    client = ComfyClient("http://127.0.0.1:8188", timeout=5.0)

    async def fake_history(prompt_id: str):
        return {
            "p1": {
                "status": {
                    "status_str": "error",
                    "completed": False,
                    "messages": [
                        [
                            "execution_error",
                            {"node_type": "KSampler", "exception_message": "OOM"},
                        ]
                    ],
                }
            }
        }

    monkeypatch.setattr(client, "get_history", fake_history)
    with pytest.raises(ComfyClientError, match="KSampler: OOM"):
        await client.wait_for_prompt("p1", poll_interval=0.0)
