"""Baseline — tables are created by SQLAlchemy create_all on startup.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-16
"""

from typing import Sequence, Union

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Greenfield schema is owned by app.db.models + create_all.
    # Future revisions should ALTER TABLE (and keep _add_column_if_missing as a safety net).
    pass


def downgrade() -> None:
    pass
