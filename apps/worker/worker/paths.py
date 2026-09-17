"""Map Docker API paths (/app/data/...) onto the host data dir."""

from __future__ import annotations

import os
from pathlib import Path


def data_root() -> Path | None:
    env = os.environ.get("INSTANTIMPACT_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    # Native worker started from apps/worker — repo data/ is two levels up
    here = Path(__file__).resolve()
    repo_data = here.parents[3] / "data"
    if repo_data.is_dir():
        return repo_data
    return None


def resolve_request_json(request_path: str, job_id: str | None = None) -> Path:
    raw = Path(str(request_path))
    if raw.is_file():
        return raw
    root = data_root()
    s = str(raw).replace("\\", "/")
    candidates: list[Path] = []
    if root:
        if "/jobs/" in s:
            rest = s.split("/jobs/", 1)[1]
            candidates.append(root / "jobs" / rest)
        if s.startswith("/app/data/"):
            candidates.append(root / s[len("/app/data/") :])
        candidates.append(root / s.lstrip("/"))
        if job_id:
            candidates.append(root / "jobs" / job_id / "request.json")
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return raw
