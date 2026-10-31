"""Explicit, version-tracked PostgreSQL schema setup for PaddyVision AI.

Run from the repository root with ``python -m api.setup_db``. This is an
additive bootstrap: SQLAlchemy creates missing tables but never alters or
drops existing columns. Any future model change that needs DDL must be added
as a new migration before deploying that model change.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, inspect, select
from sqlalchemy.engine import Connection

from api.config import PROJECT_ROOT  # noqa: F401  (ensure .env loads before database import)
from api.database import Base, engine
from api import db_models  # noqa: F401  (register ORM tables on Base.metadata)


migration_metadata = MetaData()
schema_migrations = Table(
    "schema_migrations",
    migration_metadata,
    Column("version", Integer, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)


def _initial_schema(connection: Connection) -> None:
    Base.metadata.create_all(bind=connection)


MIGRATIONS = [(1, "initial-orm-schema", _initial_schema)]


def _validate_expected_columns(connection: Connection) -> None:
    inspector = inspect(connection)
    mismatches = []
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            mismatches.append(f"{table.name}: table was not created")
            continue
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        missing = sorted(column.name for column in table.columns if column.name not in actual)
        if missing:
            mismatches.append(f"{table.name}: missing column(s) {', '.join(missing)}")
    if mismatches:
        detail = "; ".join(mismatches)
        raise RuntimeError(
            "The existing database schema does not match the current models: "
            f"{detail}. create_all() does not alter existing tables; add a new "
            "versioned migration rather than deleting the database."
        )


def migrate() -> list[str]:
    """Apply pending additive migrations and return their names."""
    applied_now: list[str] = []
    with engine.begin() as connection:
        schema_migrations.create(bind=connection, checkfirst=True)
        current = connection.execute(select(schema_migrations.c.version)).scalars().all()
        current_version = max(current, default=0)
        latest_version = MIGRATIONS[-1][0] if MIGRATIONS else 0
        if current_version > latest_version:
            raise RuntimeError(
                f"Database schema version {current_version} is newer than this code supports ({latest_version})."
            )

        for version, name, apply in MIGRATIONS:
            if version <= current_version:
                continue
            apply(connection)
            connection.execute(schema_migrations.insert().values(
                version=version,
                name=name,
                applied_at=datetime.now(timezone.utc),
            ))
            applied_now.append(name)
    with engine.connect() as connection:
        _validate_expected_columns(connection)
    return applied_now


def main() -> None:
    applied = migrate()
    if applied:
        print("Applied database migration(s): " + ", ".join(applied))
    else:
        print("Database schema is already at the latest migration.")
    print("Existing tables are not modified or dropped by this setup command.")


if __name__ == "__main__":
    main()
