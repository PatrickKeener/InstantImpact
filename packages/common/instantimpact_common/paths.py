"""Filesystem layout helpers under data/."""

from __future__ import annotations

from pathlib import Path


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


class StorageLayout:
    """Versioned storage root — all blobs live under data_dir."""

    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir).resolve()

    @property
    def db_dir(self) -> Path:
        return self.root / "db"

    @property
    def db_path(self) -> Path:
        return self.db_dir / "instantimpact.sqlite"

    @property
    def characters_dir(self) -> Path:
        return self.root / "characters"

    @property
    def jobs_dir(self) -> Path:
        return self.root / "jobs"

    @property
    def outputs_dir(self) -> Path:
        return self.root / "outputs"

    @property
    def approved_dir(self) -> Path:
        return self.root / "approved"

    @property
    def exports_dir(self) -> Path:
        return self.root / "exports"

    @property
    def models_dir(self) -> Path:
        return self.root / "models"

    def character_dir(self, character_id: str) -> Path:
        return self.characters_dir / character_id

    def version_dir(self, character_id: str, version_int: int) -> Path:
        return self.character_dir(character_id) / "versions" / f"v{version_int:03d}"

    def refs_dir(self, character_id: str, version_int: int) -> Path:
        return self.version_dir(character_id, version_int) / "refs"

    def lora_dir(self, character_id: str, version_int: int) -> Path:
        return self.version_dir(character_id, version_int) / "lora"

    def dataset_dir(self, character_id: str, version_int: int) -> Path:
        return self.version_dir(character_id, version_int) / "dataset"

    def validation_dir(self, character_id: str, version_int: int) -> Path:
        return self.version_dir(character_id, version_int) / "validation"

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def job_request_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "request.json"

    def output_stills_dir(self, character_id: str, job_id: str) -> Path:
        return self.outputs_dir / character_id / job_id / "stills"

    def approved_set_dir(self, set_id: str) -> Path:
        return self.approved_dir / set_id

    def bootstrap(self) -> None:
        for p in (
            self.db_dir,
            self.characters_dir,
            self.jobs_dir,
            self.outputs_dir,
            self.approved_dir,
            self.exports_dir,
            self.models_dir,
        ):
            ensure_dir(p)
