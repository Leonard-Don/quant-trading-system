"""baseline (matches backend/app/db/timescale_schema.sql)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-05

This revision is a deliberate no-op. The first time Alembic is wired up
on an existing database, run ``alembic stamp head`` so the version table
records that the DB is already at this revision. Future migrations will
build on top.

For a fresh database, apply ``backend/app/db/timescale_schema.sql`` first
and then ``alembic stamp head`` — same result.
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentional no-op. Schema is provided by timescale_schema.sql.
    pass


def downgrade() -> None:
    pass
