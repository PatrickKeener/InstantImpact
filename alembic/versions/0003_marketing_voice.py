"""Add marketing_voice_json to character_versions.

Revision ID: 0003_marketing_voice
Revises: 0002_products
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_marketing_voice"
down_revision: Union[str, None] = "0002_products"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("character_versions")}
    if "marketing_voice_json" not in cols:
        op.add_column(
            "character_versions",
            sa.Column("marketing_voice_json", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("character_versions")}
    if "marketing_voice_json" in cols:
        op.drop_column("character_versions", "marketing_voice_json")
