from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from worker.paths import resolve_request_json  # noqa: E402


def test_maps_docker_app_data_to_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    job = "abc-123"
    host = tmp_path / "jobs" / job
    host.mkdir(parents=True)
    target = host / "request.json"
    target.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("INSTANTIMPACT_DATA_DIR", str(tmp_path))
    found = resolve_request_json(f"/app/data/jobs/{job}/request.json", job)
    assert found == target
