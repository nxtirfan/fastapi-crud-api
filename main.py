import sqlite3
from contextlib import closing

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(
    title="Task API",
    description="A small CRUD API that manages a to-do list. "
    "Tasks are stored in a SQLite database (tasks.db), so data "
    "survives server restarts.",
    version="2.0",
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": "Invalid request body"})


SEED_TASKS = [
    {"id": 1, "title": "Learn Python basics", "done": False},
    {"id": 2, "title": "Build a CRUD API", "done": False},
    {"id": 3, "title": "Write API documentation", "done": True},
]

DB_PATH = "tasks.db"


def get_connection() -> sqlite3.Connection:
    """Open a connection to tasks.db with sensible defaults.

    Row factory gives dict-like rows; foreign keys are on for good habit.
    """
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    """Create the tasks table if missing and seed 3 example tasks only when empty.

    The seed runs inside a transaction so it is all-or-nothing.
    """
    with closing(get_connection()) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        (count,) = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()
        if count == 0:
            with connection:
                connection.executemany(
                    "INSERT INTO tasks (title, done) VALUES (?, ?)",
                    [(task["title"], int(task["done"])) for task in SEED_TASKS],
                )


init_db()


tasks: list[dict] = [dict(task) for task in SEED_TASKS]
next_id = 4


class TaskCreate(BaseModel):
    title: str | None = None
    done: bool = False


class TaskUpdate(BaseModel):
    title: str | None = None
    done: bool | None = None


def find_task(task_id: int) -> dict | None:
    return next((task for task in tasks if task["id"] == task_id), None)


@app.get("/", tags=["General"])
def read_root():
    """Describe this API: its name, version, and the endpoints it offers."""
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


@app.get("/health", tags=["General"])
def read_health():
    """Health check - returns ok as long as the server is alive."""
    return {"status": "ok"}


@app.get("/tasks", tags=["Tasks"])
def read_tasks(
    done: bool | None = Query(default=None, description="Filter: only tasks with this done status"),
    search: str | None = Query(default=None, description="Filter: case-insensitive text match on title"),
    limit: int = Query(default=0, ge=0, description="Pagination: max number of tasks to return (0 = all)"),
    offset: int = Query(default=0, ge=0, description="Pagination: number of tasks to skip"),
):
    """List tasks. Supports filtering by done status, title search, and pagination."""
    result = tasks
    if done is not None:
        result = [task for task in result if task["done"] == done]
    if search:
        needle = search.lower()
        result = [task for task in result if needle in task["title"].lower()]
    result = result[offset:]
    if limit > 0:
        result = result[:limit]
    return result


@app.get("/stats", tags=["Stats"])
def read_stats():
    """Compute summary statistics over the current task list."""
    done_count = sum(1 for task in tasks if task["done"])
    return {"total": len(tasks), "done": done_count, "open": len(tasks) - done_count}


@app.post("/reset", tags=["Tasks"])
def reset_tasks():
    """Restore the 3 seed tasks - handy for demos."""
    global next_id
    tasks[:] = [dict(task) for task in SEED_TASKS]
    next_id = 4
    return {"message": "Reset to seed tasks", "count": len(tasks)}


@app.get("/tasks/{task_id}", tags=["Tasks"])
def read_task(task_id: int):
    """Return one task by its id. Returns 404 if the id does not exist."""
    task = find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.post("/tasks", status_code=201, tags=["Tasks"])
def create_task(payload: TaskCreate):
    """Create a new task. The body must contain a non-empty title."""
    global next_id
    if payload.title is None or not payload.title.strip():
        raise HTTPException(status_code=400, detail="Field 'title' is required and must not be empty")
    task = {"id": next_id, "title": payload.title.strip(), "done": payload.done}
    tasks.append(task)
    next_id += 1
    return task


@app.put("/tasks/{task_id}", tags=["Tasks"])
def update_task(task_id: int, payload: TaskUpdate):
    """Update a task's title and/or done. Empty body or unknown id returns 400/404."""
    task = find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if payload.title is None and payload.done is None:
        raise HTTPException(status_code=400, detail="Request body must include 'title' and/or 'done'")
    if payload.title is not None:
        if not payload.title.strip():
            raise HTTPException(status_code=400, detail="Field 'title' must not be empty")
        task["title"] = payload.title.strip()
    if payload.done is not None:
        task["done"] = payload.done
    return task


@app.delete("/tasks/{task_id}", status_code=204, tags=["Tasks"])
def delete_task(task_id: int):
    """Delete a task. Returns 204 with an empty body, or 404 if the id does not exist."""
    task = find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    tasks.remove(task)
