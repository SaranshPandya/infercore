# Migrations

This project stores migrations as plain SQL files under `migrations/sql/` and includes a lightweight Python runner.

## Files

- `sql/0001_create_registry_entries.up.sql`
- `sql/0001_create_registry_entries.down.sql`

## Runner

Use the runner from Python code:

```python
from migrations.runner import run_migrations

run_migrations()
run_migrations(migration_type="down")
```

You can pass a database URL explicitly:

```python
run_migrations(database_url="sqlite:///infercore.db")
```

By default, the runner uses `INFERCORE_DATABASE_URL` and falls back to `sqlite:///infercore.db`.

The runner also creates a `schema_migrations` table to track applied versions.

It scans `migrations/sql/` dynamically, including nested subdirectories, so new migration files can be added without changing the runner.

For status checks, import and call `migration_status(...)` with a SQLAlchemy engine.

## What `0001` does

It creates the `registry_entries` table for persisted agent registry storage, including:

- unique `name`
- `description`
- `system_prompt`
- `version`
- `is_active`
- JSON `tools`
- JSON `metadata`
- `created_at`
- `updated_at`

It also creates indexes on:

- `name`
- `is_active`

## Notes

- The SQL is intentionally simple so it works as a first-pass migration for common relational databases.
- Each migration must have both an `.up.sql` and `.down.sql` file with the same base name.
- If we standardize on PostgreSQL next, we can follow this with Alembic and convert `id` to `GENERATED ... AS IDENTITY` plus stronger JSONB-specific indexing where needed.
