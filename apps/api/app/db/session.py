from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            connect_args={"check_same_thread": False},
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def _add_column_if_missing(conn, table: str, column: str, ddl: str) -> None:
    result = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
    names = {row[1] for row in result.fetchall()}
    if column not in names:
        await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


async def init_db() -> None:
    from app.db import models  # noqa: F401
    from app.db.base import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA busy_timeout=30000")
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight patches for existing SQLite files (Alembic stamps these too)
        await _add_column_if_missing(conn, "approved_sets", "export_path", "TEXT")
    _run_alembic_upgrade()


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "alembic.ini").is_file() or (p / "pyproject.toml").is_file():
            return p
    return here.parents[4]


def _run_alembic_upgrade() -> None:
    """Apply revisions. 0001 is a baseline no-op (tables come from create_all)."""
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        return

    ini = _repo_root() / "alembic.ini"
    if not ini.is_file():
        return
    settings = get_settings()
    url = settings.database_url.replace("sqlite+aiosqlite:///", "sqlite:///")
    cfg = Config(str(ini))
    cfg.set_main_option("sqlalchemy.url", url)
    try:
        command.upgrade(cfg, "head")
    except Exception as e:
        import logging

        logging.getLogger("instantimpact.db").debug("alembic upgrade skipped: %s", e)
