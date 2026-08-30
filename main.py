from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def read_root():
    """Describe this API: its name, version, and the endpoints it offers."""
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


@app.get("/health")
def read_health():
    """Health check - returns ok as long as the server is alive."""
    return {"status": "ok"}
