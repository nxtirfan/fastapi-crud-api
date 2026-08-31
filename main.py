from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import repository

app = FastAPI(
    title="Task API",
    description="A small CRUD API that manages a to-do list. "
    "Tasks are stored in PostgreSQL (run as a Docker container), "
    "so data survives restarts. All database access lives in "
    "repository.py - routes never touch the database directly.",
    version="1.0",
)


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
    return repository.list_tasks(done=done, search=search, limit=limit, offset=offset)


@app.get("/stats", tags=["Stats"])
def read_stats():
    """Compute summary statistics over the current task list."""
    return repository.count_stats()


@app.post("/reset", tags=["Tasks"])
def reset_tasks():
    """Restore the 3 seed tasks - handy for demos."""
    count = repository.reset_tasks()
    return {"message": "Reset to seed tasks", "count": count}


@app.get("/tasks/{task_id}", tags=["Tasks"])
def read_task(task_id: int):
    """Return one task by its id. Returns 404 if the id does not exist."""
    task = repository.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.post("/tasks", status_code=201, tags=["Tasks"])
def create_task(payload: TaskCreate):
    """Create a new task. The body must contain a non-empty title."""
    if payload.title is None or not payload.title.strip():
        raise HTTPException(status_code=400, detail="Field 'title' is required and must not be empty")
    return repository.create_task(title=payload.title.strip(), done=payload.done)


@app.put("/tasks/{task_id}", tags=["Tasks"])
def update_task(task_id: int, payload: TaskUpdate):
    """Update a task's title and/or done. Empty body or unknown id returns 400/404."""
    if payload.title is None and payload.done is None:
        raise HTTPException(status_code=400, detail="Request body must include 'title' and/or 'done'")
    if payload.title is not None and not payload.title.strip():
        raise HTTPException(status_code=400, detail="Field 'title' must not be empty")
    fields: dict = {}
    if payload.title is not None:
        fields["title"] = payload.title.strip()
    if payload.done is not None:
        fields["done"] = payload.done
    task = repository.update_task(task_id, fields)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.delete("/tasks/{task_id}", status_code=204, tags=["Tasks"])
def delete_task(task_id: int):
    """Delete a task. Returns 204 with an empty body, or 404 if the id does not exist."""
    if not repository.delete_task(task_id):
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
