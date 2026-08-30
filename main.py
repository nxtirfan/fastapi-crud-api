from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(
    title="Task API",
    description="A small CRUD API that manages a to-do list. "
    "All data lives in memory only - the list is reset to the "
    "3 seed tasks every time the server restarts.",
    version="1.0",
)


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


@app.get("/", tags=["General"])
def read_root():
    """Describe this API: its name, version, and the endpoints it offers."""
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


@app.get("/health", tags=["General"])
def read_health():
    """Health check - returns ok as long as the server is alive."""
    return {"status": "ok"}


@app.get("/tasks", tags=["Tasks"])
def read_tasks():
    """List all tasks."""
    return tasks


@app.get("/tasks/{task_id}", tags=["Tasks"])
def read_task(task_id: int):
    """Return one task by its id. Returns 404 if the id does not exist."""
    for task in tasks:
        if task["id"] == task_id:
            return task
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


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
    for index, task in enumerate(tasks):
        if task["id"] == task_id:
            if payload.title is None and payload.done is None:
                raise HTTPException(status_code=400, detail="Request body must include 'title' and/or 'done'")
            if payload.title is not None:
                if not payload.title.strip():
                    raise HTTPException(status_code=400, detail="Field 'title' must not be empty")
                tasks[index]["title"] = payload.title.strip()
            if payload.done is not None:
                tasks[index]["done"] = payload.done
            return tasks[index]
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@app.delete("/tasks/{task_id}", status_code=204, tags=["Tasks"])
def delete_task(task_id: int):
    """Delete a task. Returns 204 with an empty body, or 404 if the id does not exist."""
    for index, task in enumerate(tasks):
        if task["id"] == task_id:
            tasks.pop(index)
            return
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
