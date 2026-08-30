# Task API — Build Your First CRUD API (W2 · A1)

Task API — a small CRUD API that manages a to-do list, built with **Python 3 + FastAPI**. Tasks are stored in a **SQLite database** (`tasks.db`, a single file): data survives server restarts.

Built stage by stage (Stage 0 → Stage 7), one honest Git commit per stage. In Week 3 (W3 · A2), the in-memory storage was replaced with SQLite — same endpoints, same request/response shapes, only the storage layer changed.

## Why SQLite

- **Single file, zero setup.** The whole database is one file (`tasks.db`) — no database server to install or run. It is created automatically the first time the app starts.
- **Built into Python.** `sqlite3` ships with the standard library — nothing to `pip install`.
- **Survives restarts.** Unlike the Week 2 in-memory version, tasks live on disk: create a task, restart the server, it is still there.
- **The API did not change.** Clients send the same requests to the same endpoints and get the same responses. That separation — the API is the promise, the database is where the promise is kept — is the whole point of this assignment.

## Tech

- Python 3.10+ (tested on 3.14)
- FastAPI + Uvicorn
- `sqlite3` (standard library) — parameterized queries throughout, no user input glued into SQL strings
- pytest (24 automated tests, all passing — the same tests as the in-memory version, now green against SQLite)
- [DB Browser for SQLite](https://sqlitebrowser.org/) for inspecting the database by hand

## Install & Run (one command each)

```bash
# 1. Install dependencies (FastAPI/Uvicorn/pytest — sqlite3 needs no install)
pip install -r requirements.txt

# 2. Start the server on http://localhost:8000
python -m uvicorn main:app --port 8000
```

The first run creates `tasks.db` in the repo folder, the `tasks` table, and seeds 3 example tasks — only if the table is empty (restarting never duplicates the seed).

Run the test suite (optional):

```bash
python -m pytest test_main.py -v
```

## Where the database lives

`tasks.db`, in the project root, created automatically on first run. It is **git-ignored**, so a fresh clone starts with an empty database and seeds its own 3 tasks on first start — no manual setup for anyone cloning this repo.

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
| GET | `/stats` | `{total, done, open}` — computed with `SELECT COUNT(*), SUM(done)` | 200 | — |
| POST | `/reset` | Restore the 3 seed tasks | 200 | — |

Every error is JSON with an `error` key, e.g. `{"error": "Task 99 not found"}`.

### Task shape

```json
{ "id": 1, "title": "Learn Python basics", "done": false }
```

### Database schema

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0
);
```

`done` is stored as SQLite's `0`/`1` and converted to a JSON boolean at the API boundary. The database hands out ids — the app never counts them itself.

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

The same full cycle also works via Swagger UI at `/docs` → [screenshot](docs/swagger-ui.png).

## Persistence — the point of this week

I created a task ("Buy milk", id 4), confirmed `GET /tasks` showed 4 tasks, **restarted the server**, and got `GET /tasks` again: **4 tasks — "Buy milk" was still there.** Last week the same experiment ended with the task gone, because it lived only in a Python list inside the server process. This week it lives in `tasks.db` on disk, and the server's death doesn't touch it.

The seed guard matters too: the 3 example tasks are inserted only when `SELECT COUNT(*) FROM tasks` returns 0 — restart three times, still exactly 3 seed tasks, never 6, never 9.

## Opening the database by hand (Stage 4)

`tasks.db` opened in DB Browser for SQLite — the same rows the API serves, laid out like a spreadsheet → [screenshot](docs/db-browser.png).

One query I ran by hand in the "Execute SQL" tab and what it returned:

```sql
SELECT * FROM tasks WHERE done = 1;
-- returned: (3, 'Write API documentation', 1) — the single completed seed task
```

I also ran `UPDATE tasks SET done = 1;` and `DELETE FROM tasks WHERE done = 1;` directly in the viewer — and `GET /tasks` from the API reflected those changes **immediately, with no server restart**. There is no "syncing": the API and the database viewer read the exact same file. One source of truth.

## Extras

### Filtering, search & pagination — now in SQL

```
GET /tasks?done=true        → WHERE done = 1
GET /tasks?search=milk     → WHERE title LIKE '%milk%' (case-insensitive)
GET /tasks?limit=2&offset=2 → LIMIT 2 OFFSET 2
```

**What changed this week:** the filter moved from a Python loop over a list to SQL clauses the database evaluates itself — the same behaviour, but the work happens where the data lives. On a million-row table that difference stops being a detail.

### Stats & reset

```
> curl http://localhost:8000/stats
{"total":3,"done":1,"open":2}        -- SELECT COUNT(*), SUM(done) FROM tasks

> curl -X POST http://localhost:8000/reset
{"message":"Reset to seed tasks","count":3}
```

### The old mortality experiment (Week 2)

For contrast: in the in-memory version I created a task, restarted the server, and it was gone — the seed ran again and the list reset to 3. That was the limitation this assignment fixes.

## AI vs Me (W3 bonus — the rematch)

The full story — my self-written migration prompt, what the AI got right, what it silently decided, what my prompt forgot to specify, and the rematch round — is in **[ai-version/README.md](ai-version/README.md)**. My hand-built code in `main.py` stays untouched; the AI's Week 3 output lives quarantined in `ai-version/` (which also still contains the Week 2 round).

## Repo layout

```
├── main.py           # the API — hand-built, now backed by SQLite
├── test_main.py      # 24 pytest tests covering the whole CRUD cycle
├── requirements.txt  # pip install -r requirements.txt
├── docs/
│   ├── swagger-ui.png # Swagger UI screenshot
│   └── db-browser.png # DB Browser for SQLite screenshot (Stage 4)
└── ai-version/        # bonus — AI code in quarantine (W2 + W3 rounds)
    ├── main.py        # W2 Round 1 (with the bugs my prompt failed to prevent)
    ├── main_v2.py     # W2 Round 2 (after improving the prompt)
    ├── main_db.py     # W3 — AI's SQLite migration, Round 1
    ├── main_db_v2.py  # W3 — rematch round
    └── README.md      # the full "AI vs me" story (W2 + W3)
```

## Git history = one commit per stage

Week 2 (in-memory version):

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

Week 3 (SQLite migration):

```
Stage 0: create SQLite database
Stage 1: database read endpoints
Stage 2: insert into database
Stage 3: update and delete with SQL
Tests: adapt test suite to SQLite storage
Stage 4: explored SQLite
Stage 5: database documentation
Stage 6: AI vs me (AI rematch)
```

## The idea worth keeping

APIs describe what an application does. Databases describe where it stores its data. Swapping the storage did not break a single client — the same 24 tests that passed against the in-memory version pass unchanged against SQLite. Identical tests passing against a different storage is the proof that storage is just an implementation detail behind the API. Once that lands, moving to PostgreSQL or MySQL later is the same move again, wearing more clothes.
