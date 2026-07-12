"""Alembic environment: wires migrations to CollectorSettings and the ORM metadata.

The database URL always comes from ``CollectorSettings`` (i.e. the same
``CLUSTERPULSE_COLLECTOR_DATABASE_URL`` the running app uses), never from a
hardcoded value in ``alembic.ini`` — one source of truth for "where is the
database."
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from collector.config import CollectorSettings
from collector.db.base import Base
from collector.db.models import alert  # noqa: F401 - registers model on Base
from collector.db.models import metric_sample  # noqa: F401 - registers model on Base
from collector.db.models import node  # noqa: F401 - registers model on Base
from collector.db.models import remediation_action  # noqa: F401 - registers model

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", CollectorSettings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit migration SQL without a live DB connection (``--sql`` mode)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live database connection."""
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
