# AI vs Me

The AI-generated versions of this API live in this folder, quarantined from the
hand-built code in `../main.py`. I wrote the prompts myself (without copying
the assignment text), ran the AI's output against the same checkpoints I had
already passed by hand, and diffed the results. Two rounds: Week 2 (in-memory
version) and Week 3 (the SQLite migration).

Run an AI version (different port so it can run next to the hand-built one):

```bash
cd ai-version
python -m uvicorn main:app --port 8001      # W2, in-memory
python -m uvicorn main_db:app --port 8002   # W3 round 1
python -m uvicorn main_db_v2:app --port 8003 # W3 rematch
```

---

# Round 1 — Week 2: build the API in memory

## The prompt I wrote (W2, Round 1)

> Build a REST API in Python with FastAPI. It manages a to-do list and keeps
> all data in memory as a plain Python list — no database, no files. Seed the
> list with 3 example tasks, each having an id (number), title (text), and
> done (boolean).
>
> Endpoints:
> - GET / returns JSON describing the API (name, version, list of endpoints)
> - GET /health returns {"status": "ok"}
> - GET /tasks returns the whole list
> - GET /tasks/{id} returns one task; if the id does not exist return 404
> - POST /tasks creates a task from a JSON body {"title": "..."}; assign the
>   next free id, set done to false, return the created task with status 201
> - PUT /tasks/{id} updates a task's title and/or done; unknown id returns 404
> - DELETE /tasks/{id} removes a task; return 204 with an empty body; unknown
>   id returns 404
>
> Validate input: missing or empty title on POST and PUT returns 400 with a
> JSON error message. Every error response must be JSON with an "error" key.
> Add a one-line docstring to every endpoint so Swagger UI at /docs shows a
> description for each.

## What happened (quarantine results)

- **First run:** the server started without errors on the first try.
- **Stage 4 checkpoints (`curl -i`):**
  - GET /tasks → 200 PASS
  - GET /tasks/1 → 200 PASS · GET /tasks/99 → 404 PASS, but the error format
    was `{"detail": "..."}` (FastAPI default), not `{"error": "..."}` — FAIL
  - POST valid → 201 PASS · POST `{}` → **422**, not 400 — FAIL
  - PUT valid → 200 PASS · PUT `{}` → 422, not 400 — FAIL
  - DELETE → 204 PASS · DELETE unknown → 404 PASS

## Three concrete differences (diff `git diff --no-index ../main.py main.py`)

### 1. What the AI did better — and why I can explain it

The AI used a `find_task()` helper built on `next(... for ...)` (a generator
expression) once, shared by GET/PUT/DELETE, while my version wrote the same
`for ... if task["id"] == task_id` loop three times across three endpoints.
Same behavior — `next()` returns the first match or `None` — but the AI's
version is DRY. I have since adopted the pattern in my own code (see
`find_task()` in my `main.py`).

### 2. What the AI got wrong / quietly ignored

I explicitly asked for "missing or empty title returns 400" and "every error
must be JSON with an error key", but the AI left FastAPI's default
`RequestValidationError` in place (422, key `"detail"`) — two violations of
an explicitly stated rule at once. The cause: the AI declared `title: str` as
a required Pydantic field, so validation fired before my handler rules could
run, and it wrote no exception handler to override the response. Lesson: the
AI satisfied the *letter* of the endpoints while ignoring the *content* of
the status-code rules.

### 3. What my prompt forgot to specify — and the AI decided for me

My prompt never said that the 422-vs-400 error format had to be enforced via
custom exception handlers, never named the API or its version, never
mentioned Swagger tags, and never described what GET / should return. The AI
then chose its own app title ("Todo API"), returned default validation
`"detail"` bodies, and listed only `/tasks` in GET /. All reasonable choices —
but they were not mine. An incomplete specification always gets filled in
with the most common option, which is not necessarily my option.

## Rematch — the improved prompt (W2, Round 2)

> (Not copied from the assignment — my own writing, fixed based on the
> Round 1 failures above.)
>
> Build a REST API in Python 3 with FastAPI managing a to-do list. All data
> lives in memory in a plain Python list — no database, no files. Seed with
> exactly 3 tasks with fields id (int), title (str), done (bool).
>
> CRITICAL ERROR FORMAT RULE: every error response must return JSON like
> {"error": "..."} with the exact status code I name below. Do NOT let
> FastAPI's default validation produce 422 or "detail" keys. Register a
> RequestValidationError handler that returns 400 with {"error": "..."} and
> an HTTPException handler that returns {"error": ...}. Declare body fields
> as Optional in Pydantic and validate them yourself inside the handler.
>
> Endpoints and exact status codes:
> - GET / → 200, JSON {"name": "Task API", "version": "1.0",
>   "endpoints": ["/tasks"]}
> - GET /health → 200, {"status": "ok"}
> - GET /tasks → 200, whole list
> - GET /tasks/{id} → 200 one task, or 404 {"error": "Task {id} not found"}
> - POST /tasks → 201 created task (next free id, done false), or 400
>   {"error": ...} when title missing/empty
> - PUT /tasks/{id} → 200 updated task (accept title and/or done, partial
>   update), 400 when body is empty, 404 when unknown id
> - DELETE /tasks/{id} → 204 empty body, 404 when unknown id
>
> Name the app "Task API", version "1.0", group endpoints with tags, and
> write a one-line docstring per endpoint for Swagger UI at /docs.

**What changed (one sentence):** By spelling out the error format, banning
422/`detail` outright, and ordering exception handlers plus Optional fields,
Round 2 immediately produced 400 with `{"error": ...}` in every case Round 1
failed — the AI's code now passes 100% of my Stage 4 checkpoints.

---

# Round 2 — Week 3: the SQLite migration rematch

I had just moved the whole API onto SQLite by hand (Stages 0–5), so I knew
exactly what a correct memory-to-SQLite swap looks like. Time to hire the
fastest junior developer on Earth to do the same migration — and review
their work.

## The prompt I wrote (W3, Round 1)

> Migrate an in-memory FastAPI to-do API to SQLite in Python 3. Use the
> standard library sqlite3 module only — no ORM, no extra packages. The
> database file must be named tasks.db and must be created automatically on
> first run.
>
> Table: one table named tasks with columns id (INTEGER PRIMARY KEY), title
> (TEXT), done (INTEGER storing 0/1). Create the table only if it does not
> already exist.
>
> Seeding: on startup, insert 3 example tasks only if the table is empty —
> restarting the app must not duplicate them.
>
> Endpoints — keep the exact same behaviour as the in-memory version:
> - GET /tasks → 200, every task as JSON, ordered by id
> - GET /tasks/{id} → 200 one task, or 404 {"error": "Task {id} not found"}
> - POST /tasks → 201 the created task with the id the database assigned;
>   400 {"error": ...} when title is missing or empty
> - PUT /tasks/{id} → 200 the updated task (partial update: title and/or
>   done); 400 when the body is empty; 404 when the id is unknown
> - DELETE /tasks/{id} → 204 empty body; 404 when the id is unknown
>
> Safety: every query that touches user input must use parameterized
> placeholders (?). Never build SQL strings by concatenating user input.

## What happened (quarantine results)

- **First run:** started on the first try, created `tasks.db`, table, and
  its 3 seed tasks.
- **Seed check:** restart → still exactly 3 seed tasks (the count guard
  worked).
- **Persistence:** created "AI test task" (id 4), restarted the server →
  still there. Data survives.
- **Status codes:** POST → 201, PUT → 200, DELETE → 204, unknown id → 404
  `{"error": "Task 99 not found"}` — all correct, including the custom
  error format carried over from my improved W2 prompt.

## Three concrete differences (diff `git diff --no-index ../main.py main_db.py`)

### 1. What the AI did better — and why I can explain it

The AI ran `UPDATE tasks SET title = ? ... WHERE id = ?` as **two separate
single-column UPDATE statements** (one for title, one for done) instead of
building one dynamic `SET title = ?, done = ?` query like I did. Its version
is simpler to read — no list-building of `SET` clauses, no `f-string` — at
the cost of a second round-trip when both fields change. A defensible
trade-off; with two updatable columns I still prefer my single-statement
build, but I can see why a junior dev reaches for the simpler shape.

### 2. What the AI got wrong / quietly ignored

The AI's Pydantic model declared `done: int = 0` — so `done` leaked as a raw
integer through the whole API. `GET /tasks` returned `"done": 0`/`"done": 1`
instead of JSON `false`/`true` (my version converts with `bool(row["done"])`
at the API boundary), and worse: `POST {"title": "weird", "done": 5}` was
**accepted with 201** and stored `done = 5` — an invalid boolean, stored raw,
never rejected. My prompt said "INTEGER storing 0/1" for the column but never
said the API's `done` is a boolean or that non-boolean input must be
rejected. Same lesson as W2: the AI satisfies the letter and leaks the
type system it was left to choose.

### 3. What my prompt forgot to specify — and the AI decided for me

My prompt never said **which three tasks** to seed (the AI invented its own
titles — fine, they're examples), never required a fresh task to start with
`done = false` on POST (the AI made it default to 0 in the model — correct,
but its choice), and never specified connection management. The AI used a
single module-level connection with `check_same_thread=False`, shared across
all requests for the server's lifetime — it works for SQLite in practice,
but it is not a habit I want: FastAPI handlers can run on a thread pool, and
a shared connection is a hidden coupling point. My version opens a
`closing(...)` connection per request: no shared mutable state. The AI also
skipped my extras entirely (search, filter, pagination, stats, reset) —
my prompt never mentioned them, so they silently vanished from its output.

## Rematch — the improved prompt (W3, Round 2)

> (Fixed from Round 1's findings: the `done` type leak and the shared
> connection.)
>
> Migrate an in-memory FastAPI to-do API to SQLite in Python 3, standard
> library sqlite3 only. Database file tasks.db, created automatically on
> first run. Table tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL, done
> INTEGER NOT NULL DEFAULT 0), created only if missing. Seed these exact 3
> tasks only when the table is empty: ("Learn Python basics", false),
> ("Build a CRUD API", false), ("Write API documentation", true).
>
> CONNECTION RULE: do NOT keep a module-level connection. Open a fresh
> sqlite3 connection per request with contextlib.closing, set row_factory
> to sqlite3.Row, and close it when the request is done. Wrap multi-step
> writes (INSERT seed rows) in a transaction so they are all-or-nothing.
>
> TYPE RULE: done is a BOOLEAN at the API layer. Pydantic models must
> declare done as bool (TaskCreate.done defaults to False; TaskUpdate.done
> is Optional). Store it as 0/1 in SQLite (int(bool)) and convert back to
> true/false in every JSON response — the API's responses must be
> identical to the in-memory version: {"id": 1, "title": "...", "done":
> false}. A non-boolean done in a request body must be rejected with 400
> {"error": "Invalid request body"}, never accepted.
>
> Endpoints (same behavior as the in-memory version): GET /tasks → 200
> ordered by id; GET /tasks/{id} → 200 or 404 {"error": "Task {id} not
> found"}; POST /tasks → 201 created task, 400 when title missing/empty;
> PUT /tasks/{id} → 200 partial update, 400 empty body, 404 unknown id;
> DELETE /tasks/{id} → 204, 404 unknown id. Every query uses parameterized
> ? placeholders.

**What changed (one sentence):** Naming `done` a boolean end-to-end with an
explicit convert-at-the-boundary rule and banning the shared connection made
Round 2 return `"done": true/false` JSON, reject `{"done": 5}` with 400,
and open per-request connections — it now matches my hand-built version's
behavior in every checkpoint I probed.

---

# Round 3 — Week 3 · A3: the containerization rematch

I had just containerized the whole stack by hand (Stages 0–5), so I knew
what a correct app + Postgres compose stack looks like. Time to review the
fastest junior developer on Earth again.

## The prompt I wrote (A3, Round 1)

> Containerize a Python FastAPI to-do API onto PostgreSQL with Docker
> Compose. Python 3, driver psycopg (pip install "psycopg[binary]"), no
> ORM.
>
> Database: the official postgres image (any recent major version). Set
> POSTGRES_PASSWORD and POSTGRES_DB through the compose environment. The
> database URL must come from an environment variable DATABASE_URL read by
> the app — never hardcode credentials in Python. Inside the compose
> network the app connects to the database by the service name, not
> localhost.
>
> Table: tasks (id SERIAL PRIMARY KEY, title TEXT NOT NULL, done BOOLEAN
> NOT NULL DEFAULT FALSE), created automatically if missing. Seed 3 example
> tasks only when the table is empty.
>
> Endpoints (identical behavior to the in-memory version): GET /tasks →
> 200 list ordered by id; GET /tasks/{id} → 200 or 404 {"error": "Task {id}
> not found"}; POST /tasks → 201 the created task, 400 when title is
> missing/empty; PUT /tasks/{id} → 200 the updated task, accept partial
> update of title and/or done, 400 on empty body, 404 on unknown id;
> DELETE /tasks/{id} → 204 empty body, 404 on unknown id. All queries
> parameterized (%s placeholders).
>
> Deliverables: a Dockerfile for the app (Python slim base, install
> deps, run uvicorn), and a compose file with two services (app + postgres)
> so that docker compose up starts the whole stack. Data must persist
> across docker compose down then up.

## What happened (quarantine results)

- **First run:** `docker compose up` built and started both containers...
  and the app container **crashed on startup** — `psycopg.OperationalError:
  connection refused` — and stayed dead. The compose file used bare
  `depends_on: [db]`, which orders container *start*, not database
  *readiness*. Postgres needs seconds to accept connections; the app's
  `init_db()` ran into a refused connection and the process died. Only a
  manual `docker restart` brought the API up.
- **The five endpoints:** once restarted manually, all behaved correctly
  (200/201/400/204/404 with the right JSON) — the API code itself was fine.
- **Persistence — the failure the prompt warned about:** I created "AI
  stack task" (id 4), ran `docker compose down` then `up`, and the task
  was **gone** — only the 3 seed rows remained. The AI's compose file
  defines **no volume** for the postgres service, so every `down` threw the
  data away. The app "re-seeded" on the next start, which quietly masked
  the data loss: `GET /tasks` returned a plausible-looking list of 3.

## Three concrete differences (diff `git diff --no-index` on compose + storage)

### 1. What the AI did better

Its app `Dockerfile.ai` pins the app to a single copied file and installs
dependencies in one `RUN pip install` — marginally fewer layers than my
multi-step copy (I copy `requirements.txt` first for layer caching, which
is the better practice for a growing project, but the AI's version is
smaller for this codebase). Its compose file is also more readable at a
glance: no healthcheck block, no `condition` syntax — a junior reviewer
understands it immediately. Honest credit where due.

### 2. What the AI got wrong / quietly ignored

Two production-grade failures: **(a) no volume on the db service** — data
dies with every `docker compose down`, which my prompt explicitly called
out ("data must persist across down then up") and the AI ignored; **(b) no
readiness handling** — bare `depends_on` meant the app crashed on every
fresh start until Postgres happened to be up first; my hand-built stack
solves this with a `pg_isready` healthcheck + `depends_on: condition:
service_healthy`. The seed-when-empty behavior then *hid* failure (a): after
the data loss, the re-seed made the API look healthy. A quiet data-loss
bug dressed as a working system is the most dangerous kind.

### 3. What my prompt forgot to specify — and the AI decided for me

My prompt said "any recent major version" of the postgres image — the AI
pinned `postgres:17`, fine, but it could have picked `latest` (which, on
Postgres 18+, actually breaks the classic `/var/lib/postgresql/data` mount
layout I'd been assuming — I hit this myself in Stage 0 and had to pin :17).
I also never said **how** readiness should be handled (healthcheck vs
retry loop), never asked for a restart policy on the app, and never
specified the port mapping for the app service. The AI chose `8001:8000`
arbitrarily and no restart policy. All workable defaults — none of them
mine.

## Rematch — the improved prompt (A3, Round 2)

> (Fixed from Round 1's findings: the missing volume and the readiness
> crash.)
>
> Containerize a Python FastAPI to-do API onto PostgreSQL with Docker
> Compose, Python 3, psycopg driver, no ORM. Image: postgres:17 exactly.
> Database credentials only via compose environment (POSTGRES_PASSWORD,
> POSTGRES_DB) and the app reads DATABASE_URL from the environment —
> never hardcode. The app reaches the database at the compose service
> name.
>
> PERSISTENCE RULE: the db service MUST have a named volume mounted at
> /var/lib/postgresql/data so data survives docker compose down then up —
> this is a hard requirement, verify the volumes: key exists in the
> compose file.
>
> READINESS RULE: the db service MUST define a healthcheck (pg_isready)
> and the app service MUST use depends_on with condition: service_healthy
> so the app never starts before the database accepts connections. No
> bare depends_on lists.
>
> Table tasks (id SERIAL PRIMARY KEY, title TEXT NOT NULL, done BOOLEAN
> NOT NULL DEFAULT FALSE), auto-created if missing; seed 3 example tasks
> only when the table is empty. Endpoints and status codes identical to
> the in-memory version (200/201/204 success, 400 invalid body, 404
> unknown id, JSON errors with an "error" key). All queries parameterized.
>
> Deliverables: app Dockerfile (python:3.14-slim, install deps, uvicorn)
> and a compose file with services app + db, the app port mapped to host
> 8000.

**What changed (one sentence):** Promoting the volume and the healthcheck
from afterthoughts to named hard rules (PERSISTENCE RULE / READINESS RULE,
with the exact mount path and the exact `condition:` syntax) is what makes
the difference between hoping the AI includes them and knowing it will —
in the regenerated version both blocks appear, the stack survives `down`
+ `up` with data intact, and the app starts first try.

## Conclusion

An AI's output is exactly as good as its specification — and I could only
judge it because I built the thing myself first. Both halves of that
sentence are my job from now on.
