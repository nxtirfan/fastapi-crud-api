import pytest
from fastapi.testclient import TestClient

import main
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Give every test a fresh seeded database in a temporary directory."""
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "tasks.db"))
    main.init_db()
    yield


def test_root_describes_api():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_tasks():
    response = client.get("/tasks")
    assert response.status_code == 200
    assert len(response.json()) == 3


def test_get_task_by_id():
    response = client.get("/tasks/1")
    assert response.status_code == 200
    assert response.json() == {"id": 1, "title": "Learn Python basics", "done": False}


def test_get_task_404_error_format():
    response = client.get("/tasks/99")
    assert response.status_code == 404
    assert response.json() == {"error": "Task 99 not found"}


def test_create_task():
    response = client.post("/tasks", json={"title": "Buy milk"})
    assert response.status_code == 201
    assert response.json() == {"id": 4, "title": "Buy milk", "done": False}


def test_create_task_empty_title_is_400():
    response = client.post("/tasks", json={"title": ""})
    assert response.status_code == 400
    assert "error" in response.json()


def test_create_task_missing_title_is_400():
    response = client.post("/tasks", json={})
    assert response.status_code == 400
    assert "error" in response.json()


def test_create_task_invalid_body_is_400():
    response = client.post("/tasks", json=[1, 2, 3])
    assert response.status_code == 400
    assert "error" in response.json()


def test_update_task_full():
    response = client.put("/tasks/1", json={"title": "Learn Python well", "done": True})
    assert response.status_code == 200
    assert response.json() == {"id": 1, "title": "Learn Python well", "done": True}


def test_update_task_partial_title():
    response = client.put("/tasks/1", json={"title": "Learn Python deeply"})
    assert response.status_code == 200
    assert response.json() == {"id": 1, "title": "Learn Python deeply", "done": False}


def test_update_task_partial_done():
    response = client.put("/tasks/1", json={"done": True})
    assert response.status_code == 200
    assert response.json() == {"id": 1, "title": "Learn Python basics", "done": True}


def test_update_task_empty_body_is_400():
    response = client.put("/tasks/1", json={})
    assert response.status_code == 400
    assert "error" in response.json()


def test_update_task_empty_title_is_400():
    response = client.put("/tasks/1", json={"title": ""})
    assert response.status_code == 400


def test_update_task_unknown_id_is_404():
    response = client.put("/tasks/99", json={"done": True})
    assert response.status_code == 404
    assert response.json() == {"error": "Task 99 not found"}


def test_delete_task():
    response = client.delete("/tasks/2")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get("/tasks/2").status_code == 404


def test_delete_task_unknown_id_is_404():
    response = client.delete("/tasks/99")
    assert response.status_code == 404
    assert response.json() == {"error": "Task 99 not found"}


def test_filter_done():
    response = client.get("/tasks", params={"done": True})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 3


def test_search():
    response = client.get("/tasks", params={"search": "python"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 1


def test_search_case_insensitive():
    response = client.get("/tasks", params={"search": "PYTHON"})
    assert len(response.json()) == 1


def test_pagination():
    response = client.get("/tasks", params={"limit": 2, "offset": 1})
    data = response.json()
    assert len(data) == 2
    assert [task["id"] for task in data] == [2, 3]


def test_stats():
    response = client.get("/stats")
    assert response.status_code == 200
    assert response.json() == {"total": 3, "done": 1, "open": 2}


def test_reset():
    client.post("/tasks", json={"title": "Temp"})
    response = client.post("/reset")
    assert response.status_code == 200
    assert len(client.get("/tasks").json()) == 3
    created = client.post("/tasks", json={"title": "New after reset"})
    assert created.json()["id"] == 4


def test_docs_available():
    response = client.get("/docs")
    assert response.status_code == 200
