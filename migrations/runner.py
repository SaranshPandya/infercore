from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

DEFAULT_DATABASE_URL = "sqlite:///infercore.db"
MIGRATIONS_DIR = Path(__file__).resolve().parent
MIGRATIONS_SQL_DIR = MIGRATIONS_DIR / "sql"
MIGRATION_TABLE = "schema_migrations"


class MigrationError(Exception):
    pass


def _split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False

    for char in sql:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote

        if char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            continue

        current.append(char)

    trailing_statement = "".join(current).strip()
    if trailing_statement:
        statements.append(trailing_statement)

    return statements


def _discover_migrations(migrations_dir: Path) -> dict[str, Path]:
    if not migrations_dir.exists():
        raise MigrationError(f"Migration SQL directory does not exist: {migrations_dir}")

    migration_paths: dict[str, Path] = {}

    for up_file in sorted(migrations_dir.rglob("*.up.sql")):
        migration_name = up_file.relative_to(migrations_dir).as_posix().removesuffix(
            ".up.sql"
        )
        down_file = up_file.with_name(f"{up_file.name.removesuffix('.up.sql')}.down.sql")
        if not down_file.exists():
            raise MigrationError(f"Missing rollback file for migration `{migration_name}`.")
        migration_paths[migration_name] = up_file

    return migration_paths


def _ensure_migration_table(connection: Connection) -> None:
    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
                version VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


def _applied_migrations(connection: Connection) -> set[str]:
    _ensure_migration_table(connection)
    rows = connection.execute(
        text(f"SELECT version FROM {MIGRATION_TABLE} ORDER BY version")
    ).fetchall()
    return {row[0] for row in rows}


def _execute_sql(connection: Connection, sql: str) -> None:
    if connection.engine.dialect.name == "sqlite":
        connection.connection.executescript(sql)
        return

    for statement in _split_sql_statements(sql):
        connection.exec_driver_sql(statement)


def _read_sql(migrations_dir: Path, migration_name: str, direction: str) -> str:
    file_path = migrations_dir / f"{migration_name}.{direction}.sql"
    return file_path.read_text(encoding="utf-8")


def _pending_migrations(all_migrations: Iterable[str], applied: set[str]) -> list[str]:
    return [migration for migration in all_migrations if migration not in applied]


def apply_migrations(
    engine: Engine,
    migrations_dir: Path = MIGRATIONS_SQL_DIR,
    *,
    steps: int,
) -> list[str]:
    if steps < 1:
        raise MigrationError("`steps` must be at least 1.")

    migration_paths = _discover_migrations(migrations_dir)
    all_migrations = list(migration_paths)

    with engine.begin() as connection:
        applied = _applied_migrations(connection)
        pending = _pending_migrations(all_migrations, applied)[:steps]

        for migration_name in pending:
            _execute_sql(connection, _read_sql(migrations_dir, migration_name, "up"))
            connection.execute(
                text(f"INSERT INTO {MIGRATION_TABLE} (version) VALUES (:version)"),
                {"version": migration_name},
            )

    return pending


def rollback_migrations(
    engine: Engine,
    migrations_dir: Path = MIGRATIONS_SQL_DIR,
    *,
    steps: int,
) -> list[str]:
    if steps < 1:
        raise MigrationError("`steps` must be at least 1.")

    migration_paths = _discover_migrations(migrations_dir)

    with engine.begin() as connection:
        applied = sorted(_applied_migrations(connection), reverse=True)[:steps]

        for migration_name in applied:
            if migration_name not in migration_paths:
                raise MigrationError(
                    f"Cannot roll back `{migration_name}` because its SQL files are missing."
                )
            _execute_sql(connection, _read_sql(migrations_dir, migration_name, "down"))
            connection.execute(
                text(f"DELETE FROM {MIGRATION_TABLE} WHERE version = :version"),
                {"version": migration_name},
            )

    return applied


def migration_status(
    engine: Engine,
    migrations_dir: Path = MIGRATIONS_SQL_DIR,
) -> list[dict[str, Any]]:
    all_migrations = list(_discover_migrations(migrations_dir))

    with engine.begin() as connection:
        applied = _applied_migrations(connection)

    return [
        {
            "version": migration_name,
            "applied": migration_name in applied,
        }
        for migration_name in all_migrations
    ]


def run_migrations(
    *,
    migration_type: Literal["up", "down"] = "up",
    database_url: str | None = None,
    steps: int = 1,
    migrations_dir: Path = MIGRATIONS_SQL_DIR,
) -> list[str]:
    engine = create_engine(
        database_url or os.getenv("INFERCORE_DATABASE_URL", DEFAULT_DATABASE_URL)
    )

    if migration_type == "down":
        return rollback_migrations(engine, migrations_dir=migrations_dir, steps=steps)

    return apply_migrations(engine, migrations_dir=migrations_dir, steps=steps)
