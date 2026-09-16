from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import get_settings
from instantimpact_common.paths import StorageLayout, ensure_dir


def get_layout() -> StorageLayout:
    settings = get_settings()
    layout = StorageLayout(settings.resolved_data_dir())
    layout.bootstrap()
    return layout


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def relative_to_data(path: Path) -> str:
    layout = get_layout()
    try:
        return str(path.resolve().relative_to(layout.root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def resolve_under_root(rel: str, root: Path | None = None) -> Path | None:
    """Resolve a relative path under data/, rejecting traversal."""
    layout_root = (root or get_layout().root).resolve()
    rel_n = str(rel).replace("\\", "/").lstrip("/")
    target = (layout_root / rel_n).resolve()
    try:
        target.relative_to(layout_root)
    except ValueError:
        return None
    return target
