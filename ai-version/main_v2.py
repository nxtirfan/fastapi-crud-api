"""Round 2 of the AI rematch: same API, prompt improved from Round 1.

The README.md in this folder documents what the improved prompt fixed:
400 with {"error": ...} everywhere instead of 422/{"detail": ...}.
Run on port 8001 so it can be compared side by side with the manual version.
"""
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Task API", version="1.0")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": "Invalid request body"})


tasks = [
    {"id": 1, "title": "Learn Python basics", "done": False},
    {"id": 2, "title": "Build a CRUD API", "done": False},
    {"id": 3, "title": "Write API documentation", "done": True},
]
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
    """Describe this API."""
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


@app.get("/health", tags=["General"])
def read_health():
    """Health check."""
    return {"status": "ok"}


@app.get("/tasks", tags=["Tasks"])
def read_tasks(
    done: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=0, ge=0),
    offset: int = Query(default=0, ge=0),
):
    """List tasks with optional filtering, search, and pagination."""
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


@app.get("/tasks/{task_id}", tags=["Tasks"])
def read_task(task_id: int):
    """Get one task by id."""
    task = find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.post("/tasks", status_code=201, tags=["Tasks"])
def create_task(payload: TaskCreate):
    """Create a new task with a non-empty title."""
    global next_id
    if payload.title is None or not payload.title.strip():
        raise HTTPException(status_code=400, detail="Field 'title' is required and must not be empty")
    task = {"id": next_id, "title": payload.title.strip(), "done": payload.done}
    tasks.append(task)
    next_id += 1
    return task


@app.put("/tasks/{task_id}", tags=["Tasks"])
def update_task(task_id: int, payload: TaskUpdate):
    """Update title and/or done of one task (partial update)."""
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
    """Delete one task."""
    task = find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    tasks.remove(task)
