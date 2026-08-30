from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

app = FastAPI(title="Todo API", version="1.0.0")

tasks = [
    {"id": 1, "title": "Learn Python basics", "done": False},
    {"id": 2, "title": "Build a CRUD API", "done": False},
    {"id": 3, "title": "Write API documentation", "done": True},
]
next_id = 4


class TaskCreate(BaseModel):
    title: str
    done: bool = False


class TaskUpdate(BaseModel):
    title: str | None = None
    done: bool | None = None


def find_task(task_id: int) -> dict | None:
    return next((task for task in tasks if task["id"] == task_id), None)


@app.get("/")
def read_root():
    """Describe the API."""
    return {"name": "Todo API", "version": "1.0.0", "endpoints": ["/tasks"]}


@app.get("/health")
def read_health():
    """Health check."""
    return {"status": "ok"}


@app.get("/tasks")
def read_tasks(
    done: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=0, ge=0),
    offset: int = Query(default=0, ge=0),
):
    """List tasks with optional filters."""
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


@app.get("/tasks/{task_id}")
def read_task(task_id: int):
    """Get one task by id."""
    task = find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.post("/tasks", status_code=201)
def create_task(payload: TaskCreate):
    """Create a new task."""
    global next_id
    task = {"id": next_id, "title": payload.title.strip(), "done": payload.done}
    tasks.append(task)
    next_id += 1
    return task


@app.put("/tasks/{task_id}")
def update_task(task_id: int, payload: TaskUpdate):
    """Update a task (title and/or done)."""
    task = find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if payload.title is not None:
        task["title"] = payload.title.strip()
    if payload.done is not None:
        task["done"] = payload.done
    return task


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int):
    """Delete a task."""
    task = find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    tasks.remove(task)
