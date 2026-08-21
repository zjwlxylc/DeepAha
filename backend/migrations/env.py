from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from deepaha.core.settings import Settings
from deepaha.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    value = Settings().database_url
    if value is None:
        raise RuntimeError("DEEPAHA_DATABASE_URL is required for Alembic")
    return value.replace("%", "%%")


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Phase 1 Alembic configuration supports online migrations only")

run_migrations_online()
