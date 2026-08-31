"""Repository: the one module that talks to the database.

Swapping storage (in-memory -> SQLite -> Postgres) touches only this file;
routes and responses stay identical. Parameterized queries throughout.
"""

import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

SEED_TASKS = [
    ("Learn Python basics", False),
    ("Build a CRUD API", False),
    ("Write API documentation", True),
]


def _connect() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)


def _row_to_task(row: tuple) -> dict:
    task_id, title, done = row
    return {"id": task_id, "title": title, "done": done}


def init_db() -> None:
    """Create the tasks table if missing and seed 3 example tasks only when empty."""
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                done BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
        (count,) = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()
        if count == 0:
            with connection.transaction(), connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO tasks (title, done) VALUES (%s, %s)", SEED_TASKS
                )


def list_tasks(done: bool | None = None, search: str | None = None,
               limit: int = 0, offset: int = 0) -> list[dict]:
    """List tasks with optional done-filter, case-insensitive title search, pagination."""
    clauses = []
    params: list = []
    if done is not None:
        clauses.append("done = %s")
        params.append(done)
    if search:
        clauses.append("title ILIKE %s")
        params.append(f"%{search}%")
    query = "SELECT * FROM tasks"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id"
    if limit > 0:
        query += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
    elif offset > 0:
        query += " LIMIT ALL OFFSET %s"
        params.append(offset)
    with _connect() as connection:
        rows = connection.execute(query, params).fetchall()
        return [_row_to_task(row) for row in rows]


def get_task(task_id: int) -> dict | None:
    """Fetch one task by id, or None if it does not exist."""
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM tasks WHERE id = %s", (task_id,)
        ).fetchone()
        return _row_to_task(row) if row is not None else None


def create_task(title: str, done: bool) -> dict:
    """Insert a task; the database assigns the id (RETURNING hands it back)."""
    with _connect() as connection:
        row = connection.execute(
            "INSERT INTO tasks (title, done) VALUES (%s, %s) RETURNING *",
            (title, done),
        ).fetchone()
        return _row_to_task(row)


def update_task(task_id: int, fields: dict) -> dict | None:
    """Update title and/or done; returns the updated task or None if unknown id."""
    if not fields:
        return get_task(task_id)
    sets = ", ".join(f"{column} = %s" for column in fields)
    params = list(fields.values()) + [task_id]
    with _connect() as connection:
        row = connection.execute(
            f"UPDATE tasks SET {sets} WHERE id = %s RETURNING *", params
        ).fetchone()
        return _row_to_task(row) if row is not None else None


def delete_task(task_id: int) -> bool:
    """Delete a task; returns True if a row was removed, False if unknown id."""
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
        return cursor.rowcount > 0


def count_stats() -> dict:
    """Total/done/open counts, computed by Postgres aggregates."""
    with _connect() as connection:
        (total, done) = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(CAST(done AS INT)), 0) FROM tasks"
        ).fetchone()
        return {"total": total, "done": done, "open": total - done}


def reset_tasks() -> int:
    """Delete everything and reseed the 3 example tasks; returns the new count."""
    with _connect() as connection:
        connection.execute("DELETE FROM tasks")
        with connection.transaction(), connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO tasks (title, done) VALUES (%s, %s)", SEED_TASKS
            )
        (count,) = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()
        return count
