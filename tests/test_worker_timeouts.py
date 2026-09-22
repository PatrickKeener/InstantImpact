"""The whole-job timeout must outlast every inner timeout it contains.

arq's default job_timeout is 300s, which silently truncated stills batches
partway through and killed LoRA training runs. These pin the ordering.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for rel in ("apps/worker", "packages/common", "packages/comfy_client", "packages/prompt_engine"):
    sys.path.insert(0, str(ROOT / rel))

ARQ_DEFAULT_JOB_TIMEOUT = 300


def _worker_settings(monkeypatch, value: str | None):
    monkeypatch.delenv("INSTANTIMPACT_JOB_TIMEOUT", raising=False)
    if value is not None:
        monkeypatch.setenv("INSTANTIMPACT_JOB_TIMEOUT", value)
    import worker.main as wm

    return importlib.reload(wm).WorkerSettings


def test_job_timeout_is_set_and_beats_arq_default(monkeypatch):
    settings = _worker_settings(monkeypatch, None)
    assert settings.job_timeout > ARQ_DEFAULT_JOB_TIMEOUT
    assert settings.job_timeout == 14400.0


def test_job_timeout_covers_a_realistic_full_batch(monkeypatch):
    """Seed galleries allow 40 stills. Budget against realistic per-still cost.

    The pathological bound is 40 * INSTANTIMPACT_COMFY_TIMEOUT (24000s), which
    is deliberately *not* covered: that only happens when Comfy is wedged and
    every item burns its full per-prompt timeout, and in that state failing is
    better than spending 6+ hours confirming it. A healthy still with the
    hi-res pass runs well under 200s on the target GPU, so this leaves headroom.
    """
    settings = _worker_settings(monkeypatch, None)
    max_batch, slow_still = 40, 200.0
    assert settings.job_timeout >= max_batch * slow_still


def test_job_timeout_dwarfs_a_single_prompt_timeout(monkeypatch):
    """A single slow item must never be able to consume the whole job budget."""
    settings = _worker_settings(monkeypatch, None)
    assert settings.job_timeout >= 10 * 600.0


def test_job_timeout_covers_the_training_gpu_lock_ceiling(monkeypatch):
    """train.py holds the GPU lock for 4h, so the job must be allowed to live that long."""
    settings = _worker_settings(monkeypatch, None)
    assert settings.job_timeout >= 14400.0


def test_job_timeout_env_override(monkeypatch):
    assert _worker_settings(monkeypatch, "7200").job_timeout == 7200.0


def test_job_timeout_ignores_malformed_env(monkeypatch):
    assert _worker_settings(monkeypatch, "not-a-number").job_timeout == 14400.0
    assert _worker_settings(monkeypatch, "   ").job_timeout == 14400.0
