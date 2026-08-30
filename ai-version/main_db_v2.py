import sqlite3
from contextlib import closing

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Task API", version="1.0")

DB_FILE = "tasks.db"
SEEDS = [
    ("Learn Python basics", 0),
    ("Build a CRUD API", 0),
    ("Write API documentation", 1),
]


def get_connection():
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with closing(get_connection()) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            "id INTEGER PRIMARY KEY, "
            "title TEXT NOT NULL, "
            "done INTEGER NOT NULL DEFAULT 0"
            ")"
        )
        connection.commit()
        count = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        if count == 0:
            with connection:
                connection.executemany(
                    "INSERT INTO tasks (title, done) VALUES (?, ?)", SEEDS
                )


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


def row_to_task(row):
    return {"id": row["id"], "title": row["title"], "done": bool(row["done"])}


def get_task(task_id: int):
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return row_to_task(row) if row else None


@app.get("/tasks")
def list_tasks():
    with closing(get_connection()) as connection:
        rows = connection.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        return [row_to_task(row) for row in rows]


@app.get("/tasks/{task_id}")
def read_task(task_id: int):
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.post("/tasks", status_code=201)
def create_task(payload: TaskCreate):
    if payload.title is None or not payload.title.strip():
        raise HTTPException(
            status_code=400,
            detail="Field 'title' is required and must not be empty",
        )
    with closing(get_connection()) as connection:
        with connection:
            cursor = connection.execute(
                "INSERT INTO tasks (title, done) VALUES (?, ?)",
                (payload.title.strip(), int(payload.done)),
            )
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return row_to_task(row)


@app.put("/tasks/{task_id}")
def update_task(task_id: int, payload: TaskUpdate):
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if payload.title is None and payload.done is None:
        raise HTTPException(
            status_code=400,
            detail="Request body must include 'title' and/or 'done'",
        )
    if payload.title is not None and not payload.title.strip():
        raise HTTPException(status_code=400, detail="Field 'title' must not be empty")
    sets = []
    params = []
    if payload.title is not None:
        sets.append("title = ?")
        params.append(payload.title.strip())
    if payload.done is not None:
        sets.append("done = ?")
        params.append(int(payload.done))
    params.append(task_id)
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params
            )
    return get_task(task_id)


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int):
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    with closing(get_connection()) as connection:
        with connection:
            connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
