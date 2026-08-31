"""AI-generated containerized version (Round 1) - lives in quarantine.

Written from the user's prompt; contains deliberate review findings vs the
hand-built stack (missing volume, no healthcheck, hardcoded-ish compose).
Do not run as the submission - see ai-version/README.md.
"""

import os

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Task API", version="1.0")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgres://postgres:dev@localhost:5432/tasks")


def get_connection():
    return psycopg.connect(DATABASE_URL)


def init_db():
    with get_connection() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            "id SERIAL PRIMARY KEY, title TEXT NOT NULL, done BOOLEAN DEFAULT FALSE)"
        )
        count = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        if count == 0:
            connection.execute("INSERT INTO tasks (title, done) VALUES (%s, %s)",
                               ("Learn Python basics", False))
            connection.execute("INSERT INTO tasks (title, done) VALUES (%s, %s)",
                               ("Build a CRUD API", False))
            connection.execute("INSERT INTO tasks (title, done) VALUES (%s, %s)",
                               ("Write API documentation", True))


init_db()


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": "Invalid request body"})


class TaskCreate(BaseModel):
    title: str | None = None
    done: bool = False


class TaskUpdate(BaseModel):
    title: str | None = None
    done: bool | None = None


@app.get("/tasks")
def list_tasks():
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        return [{"id": r[0], "title": r[1], "done": r[2]} for r in rows]


@app.get("/tasks/{task_id}")
def read_task(task_id: int):
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return {"id": row[0], "title": row[1], "done": row[2]}


@app.post("/tasks", status_code=201)
def create_task(payload: TaskCreate):
    if not payload.title or not payload.title.strip():
        raise HTTPException(status_code=400, detail="Field 'title' is required and must not be empty")
    with get_connection() as connection:
        row = connection.execute(
            "INSERT INTO tasks (title, done) VALUES (%s, %s) RETURNING *",
            (payload.title.strip(), payload.done),
        ).fetchone()
    return {"id": row[0], "title": row[1], "done": row[2]}


@app.put("/tasks/{task_id}")
def update_task(task_id: int, payload: TaskUpdate):
    if payload.title is None and payload.done is None:
        raise HTTPException(status_code=400, detail="Request body must include 'title' and/or 'done'")
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        connection.execute(
            "UPDATE tasks SET title = %s, done = %s WHERE id = %s",
            (payload.title.strip() if payload.title else row[1],
             payload.done if payload.done is not None else row[2],
             task_id),
        )
        updated = connection.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()
    return {"id": updated[0], "title": updated[1], "done": updated[2]}


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int):
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
