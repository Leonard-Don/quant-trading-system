"""Alembic environment for the quant-trading-system backend.

Reads ``DATABASE_URL`` from the OS environment (the same env var
``backend.app.core.persistence`` consults). No SQLAlchemy ORM models are
declared in this project, so ``target_metadata`` is None — autogenerate
will not produce useful diffs. Migrations are written by hand.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _resolve_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL must be set to run Alembic migrations. "
            "Example: postgresql+psycopg://user:pass@localhost:5432/quant"
        )
    # Alembic expects a SQLAlchemy URL; if the env value is plain
    # ``postgresql://...`` it works as-is.
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _resolve_database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
