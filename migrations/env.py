"""Alembic environment — DATABASE_URL from the environment wins."""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.getenv("DATABASE_URL", "")
if database_url:
    # the app uses psycopg3; SQLAlchemy needs the explicit driver name
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    config.set_main_option("sqlalchemy.url", database_url)
elif not config.get_main_option("sqlalchemy.url"):
    sys.exit("DATABASE_URL is not set and alembic.ini has no sqlalchemy.url")

target_metadata = None  # hand-written migrations; no autogenerate against a
# live app schema (storage.init() remains the fresh-bootstrap path until the
# migrations fully own the schema — see DELTA_PLAN.md PR-3).


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
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
