# Task API — Build Your First CRUD API (W2 · A1)

Task API — a small CRUD API that manages a to-do list, built with **Python 3 + FastAPI**. All data lives **in memory only** (no database, no files): the list is re-seeded with 3 example tasks every time the server restarts.

Built stage by stage (Stage 0 → Stage 7), one honest Git commit per stage.

## Tech

- Python 3.10+ (tested on 3.14)
- FastAPI + Uvicorn
- pytest (24 automated tests, all passing)
- Swagger UI: built into FastAPI at `/docs` — zero setup

## Install & Run (one command each)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server on http://localhost:8000
python -m uvicorn main:app --port 8000
```

Then open:

- Swagger UI: http://localhost:8000/docs
- Interactive alternative (no terminal needed): https://hoppscotch.io

Run the test suite (optional):

```bash
python -m pytest test_main.py -v
```

## Endpoints

| Method | Path | Meaning | Success | Errors |
|---|---|---|---|---|
| GET | `/` | Describe the API (name, version, endpoints) | 200 | — |
| GET | `/health` | Is the server alive? | 200 | — |
| GET | `/tasks` | List all tasks (`?done=`, `?search=`, `?limit=`, `?offset=`) | 200 | — |
| GET | `/tasks/{id}` | Get one task | 200 | 404 |
| POST | `/tasks` | Create a task (`{"title": "..."}`) | 201 | 400 |
| PUT | `/tasks/{id}` | Update title and/or done (partial update) | 200 | 400, 404 |
| DELETE | `/tasks/{id}` | Remove a task | 204 (empty body) | 404 |
| GET | `/stats` | `{total, done, open}` — the server computes something | 200 | — |
| POST | `/reset` | Restore the 3 seed tasks | 200 | — |

Every error is JSON with an `error` key, e.g. `{"error": "Task 99 not found"}`.

### Task shape

```json
{ "id": 1, "title": "Learn Python basics", "done": false }
```

## The full CRUD cycle, via `curl -i`

Create:

```
> curl -i -X POST http://localhost:8000/tasks -H "Content-Type: application/json" -d '{"title":"Buy milk"}'
HTTP/1.1 201 Created
content-type: application/json

{"id":4,"title":"Buy milk","done":false}
```

Read (list + one):

```
> curl -i http://localhost:8000/tasks
HTTP/1.1 200 OK
content-type: application/json

[{"id":1,"title":"Learn Python basics","done":false},{"id":2,"title":"Build a CRUD API","done":false},{"id":3,"title":"Write API documentation","done":true},{"id":4,"title":"Buy milk","done":false}]

> curl -i http://localhost:8000/tasks/4
HTTP/1.1 200 OK

{"id":4,"title":"Buy milk","done":false}
```

Update (mark it done):

```
> curl -i -X PUT http://localhost:8000/tasks/4 -H "Content-Type: application/json" -d '{"done":true}'
HTTP/1.1 200 OK

{"id":4,"title":"Buy milk","done":true}
```

Delete:

```
> curl -i -X DELETE http://localhost:8000/tasks/4
HTTP/1.1 204 No Content

(no body — success with nothing to say)
```

A stranger knocking on a wrong door:

```
> curl -i http://localhost:8000/tasks/99
HTTP/1.1 404 Not Found

{"error":"Task 99 not found"}
```

The same full cycle also works via Swagger UI → [screenshot](docs/swagger-ui.png) — every endpoint visible with its "Try it out" button.

## Extras

### Filtering, search & pagination

```
GET /tasks?done=true        → only finished tasks
GET /tasks?search=milk      → tasks whose title contains "milk" (case-insensitive)
GET /tasks?limit=2&offset=2 → third page of two items
```

**Why real APIs never return "everything":** the list in memory is tiny, but a real API sits on top of tables with millions of rows — returning "everything" would mean enormous responses, slow queries, and an easy way for one client to exhaust the server (accidentally or on purpose). Pagination caps the cost of any single request: the client asks for a window, not the whole warehouse.

### Stats & reset

```
> curl http://localhost:8000/stats
{"total":3,"done":1,"open":2}

> curl -X POST http://localhost:8000/reset
{"message":"Reset to seed tasks","count":3}
```

### The mortality experiment

I created a task ("Buy milk", id 4), confirmed `GET /tasks` showed 4 tasks, restarted the server, and got `GET /tasks` again: **3 tasks — "Buy milk" was gone.** The task lived only in a Python list inside the server process; restarting the process threw that memory away and the seed data ran again. Data that matters needs to live somewhere the server's death doesn't touch — that is exactly what a database is for, which is next week.

## AI vs Me (Stage 7 — bonus)

The full story — my self-written prompt, what the AI got right, what it silently ignored (422/`detail` instead of 400/`error`), what my prompt forgot to specify, and the one-sentence rematch result — is in **[ai-version/README.md](ai-version/README.md)**. My hand-built code in `main.py` stays untouched; the AI's output lives quarantined in `ai-version/`.

## Repo layout

```
├── main.py           # the API — hand-built, stages 0–6
├── test_main.py      # 24 pytest tests covering the whole CRUD cycle
├── requirements.txt  # pip install -r requirements.txt
├── docs/
│   └── swagger-ui.png # Swagger UI screenshot
└── ai-version/        # Stage 7 bonus — AI code in quarantine
    ├── main.py        # Round 1 (with the bugs my prompt failed to prevent)
    ├── main_v2.py     # Round 2 (after improving the prompt)
    └── README.md      # the full "AI vs me" story
```

## Git history = one commit per stage

```
Stage 0: hello server
Stage 1: root and health endpoints
Stage 2: read endpoints with 404
Stage 3: create with validation
Stage 4: full CRUD
Stage 5: Swagger UI
Stage 6: publish and docs
Extras: filtering, search, pagination, stats, reset
Tests: automated test suite
Stage 7: AI vs me
```
