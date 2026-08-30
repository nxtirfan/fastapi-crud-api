import sqlite3

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Task API", version="1.0")

DB_FILE = "tasks.db"
SEEDS = [
    ("Learn SQLite basics", 0),
    ("Write first SQL queries", 0),
    ("Backup the database", 1),
]

connection = sqlite3.connect(DB_FILE, check_same_thread=False)
connection.row_factory = sqlite3.Row


def init_db():
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
        connection.executemany(
            "INSERT INTO tasks (title, done) VALUES (?, ?)", SEEDS
        )
        connection.commit()


init_db()


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": "Invalid request body"})


class TaskCreate(BaseModel):
    title: str | None = None
    done: int = 0


class TaskUpdate(BaseModel):
    title: str | None = None
    done: int | None = None


def get_task(task_id: int):
    row = connection.execute(
        "SELECT * FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()
    return dict(row) if row else None


@app.get("/tasks")
def list_tasks():
    rows = connection.execute("SELECT * FROM tasks ORDER BY id").fetchall()
    return [dict(row) for row in rows]


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
    cursor = connection.execute(
        "INSERT INTO tasks (title, done) VALUES (?, ?)",
        (payload.title.strip(), payload.done),
    )
    connection.commit()
    return {
        "id": cursor.lastrowid,
        "title": payload.title.strip(),
        "done": payload.done,
    }


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
    if payload.title is not None:
        if not payload.title.strip():
            raise HTTPException(
                status_code=400, detail="Field 'title' must not be empty"
            )
        connection.execute(
            "UPDATE tasks SET title = ? WHERE id = ?", (payload.title.strip(), task_id)
        )
    if payload.done is not None:
        connection.execute(
            "UPDATE tasks SET done = ? WHERE id = ?", (payload.done, task_id)
        )
    connection.commit()
    return get_task(task_id)


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int):
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    connection.commit()
