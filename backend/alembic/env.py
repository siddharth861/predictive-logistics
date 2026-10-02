import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context


# Make the backend application package available to Alembic.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from app.models import Base


config = context.config


if config.config_file_name is not None:
    fileConfig(config.config_file_name)


target_metadata = Base.metadata


def include_object(
    object,
    name,
    type_,
    reflected,
    compare_to,
):
    """
    Prevent Alembic from trying to remove database tables
    that are not part of our application's SQLAlchemy metadata.

    This is especially important because PostGIS creates
    its own internal tables and metadata.
    """

    if type_ == "table" and reflected and compare_to is None:
        return False

    return True


def run_migrations_offline() -> None:
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://logistics_user:logistics_dev_password@postgres:5432/logistics",
    )

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named",
        },
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://logistics_user:logistics_dev_password@postgres:5432/logistics",
    )

    connectable = engine_from_config(
        {
            "sqlalchemy.url": database_url,
        },
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()