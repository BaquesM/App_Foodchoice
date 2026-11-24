"""Alembic environment: uses the application's engine and models metadata."""
from alembic import context

from backend.app.db.session import Base, engine
from backend.app.models import recipe  # noqa: F401  (registers all models)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite cannot ALTER/DROP columns natively: Alembic rebuilds the table instead
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
