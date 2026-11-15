# Task API — Build Your First CRUD API (W2 · A1) + Put an LLM behind your API (W7 · A17)

Task API — a small CRUD API that manages a to-do list, built with **Python 3 + FastAPI**. Tasks are stored in **PostgreSQL, running as a Docker container**: the whole stack (app + database) starts with one command, `docker compose up`.

As of W7 it also carries one LLM endpoint, **`POST /enrich`**: it takes a messy book record (from the Week 5 scraper) and returns clean, schema-validated JSON — a category, a one-sentence summary, quality flags, and a confidence — with a real timeout, a retry policy, a cost log and a kill switch. Details in [JOB-CARD.md](JOB-CARD.md) and the "Enrich" section below.

Built stage by stage, one honest Git commit per stage. Storage has been swapped three times in this repo, and the API never changed:

| Version | Where tasks live | What runs it |
|---|---|---|
| A1 (Week 2) | a list in memory | the Python process |
| A2 (Week 3) | `tasks.db`, a single file | SQLite on disk |
| A3 (Week 3, current) | rows in Postgres | a Docker container — a real database server |

## One command runs everything

```bash
cp .env.example .env       # set DATABASE_URL (host:port come from compose)
docker compose up         # app + Postgres, together
```

That's it: `docker compose up` builds the app image, starts Postgres 17 with a named volume (`taskdata`), waits until the database passes its healthcheck, then starts the API on **http://localhost:8000**. The `tasks` table and 3 seed rows are created automatically on first run (seed only when the table is empty — restarts never duplicate them).

- Swagger UI: http://localhost:8000/docs
- Stop everything: `docker compose down` (data survives — it lives in the volume, not the container)

### Running without Docker (local dev)

```bash
pip install -r requirements.txt
python -m uvicorn main:app --port 8000
```

This expects a Postgres reachable at `DATABASE_URL` from `.env` (e.g. the standalone container from Stage 0: `docker run --name taskdb -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=tasks -p 5432:5432 -v taskdata:/var/lib/postgresql/data -d postgres:17`).

### Configuration

All config comes from the environment — nothing is hardcoded. Copy `.env.example` to `.env` and adjust:

```
DATABASE_URL=postgres://postgres:dev@localhost:5432/tasks
```

Inside the compose network the app reaches the database by **service name** (`db`), not `localhost` — compose sets `DATABASE_URL` itself for the container; your `.env` matters only for running the app outside Docker. `.env` is git-ignored; `.env.example` is committed, so no real credentials ever enter git history.

## Tech

- Python 3.10+ (tested on 3.14), FastAPI + Uvicorn
- `psycopg` 3 (Postgres driver) — every query parameterized (`%s` placeholders); user input is never glued into SQL strings
- PostgreSQL 17 (official Docker image) with a named volume for persistence
- Docker + Docker Compose — `Dockerfile` (app image) + `compose.yaml` (app + db, one command)
- pytest (42 automated tests, all passing — 24 covering the whole CRUD cycle since A1, 18 covering the LLM plumbing: parse, repair-once, quarantine, retry policy, kill switch)

## Architecture — the repository pattern

```
routes (main.py)  ->  repository (repository.py)  ->  Postgres (container)
```

`main.py` contains only routes, validation, and status codes. **Every line that talks to the database lives in `repository.py`** — the one-module rule from the assignment. Proof it held: moving SQLite → Postgres touched `repository.py` (rewrite) and `main.py` (import + call sites only, no route logic), and the same 24 tests kept passing. Storage is an implementation detail behind the API — that is the whole point of this repo's three storage swaps.

### Database schema

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    done BOOLEAN NOT NULL DEFAULT FALSE
);
```

Postgres hands out ids (`SERIAL`); `done` is a real boolean end-to-end — no 0/1 conversion at the boundary this time.

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
| GET | `/stats` | `{total, done, open}` — computed with Postgres aggregates | 200 | — |
| POST | `/reset` | Restore the 3 seed tasks | 200 | — |
| POST | `/enrich` | Enrich one scraped book record via an LLM (W7) | 200 | 400, 422, 502, 503, 504 |

Every error is JSON with an `error` key, e.g. `{"error": "Task 99 not found"}`.

### The LLM endpoint — `POST /enrich` (W7 · A17)

Input: one record as scraped in Week 5. Output: the same four fields every time — category from a closed list of six, a one-sentence summary, 1–3 quality flags, and a confidence. The model's answer is parsed, validated against the Pydantic schema, repaired once if broken, and quarantined with a 422 if still broken. Raw model text is never returned.

**Reliability policy (Stage 4), all explicit, no SDK defaults left in place:** the client timeout is 30 s (the SDK would silently wait ten minutes), and the SDK's own two hidden retries are switched off (`max_retries=0`) — this module owns the retry policy instead. Retries fire **only** on timeouts, 429 and 5xx, with exponential backoff plus jitter (1s/2s/4s + up to 0.5s random), honouring `Retry-After` on a 429; a 400/401/403 is never retried and fails fast as `502`. Retries exhausted → `504`. Every attempt writes one structured JSON log line to stdout — `prompt_version`, `model`, `prompt_tokens`, `completion_tokens`, `duration_ms`, `attempt` — so cost is a `grep` away. `LLM_ENABLED=false` is the kill switch: the endpoint answers immediately with a deterministic `503` and no model call.

An answer that fails twice is appended to `logs/quarantine.jsonl` (input, error, prompt version, raw output) — the log exists precisely so the failure is inspectable, not swallowed.

One honest note from testing the failure path live (2026-11-15, model routed to `baidu/ernie-5.5-flash-preview:free`): I temporarily poisoned the prompt twice — first with an instruction to use a category outside the list, then by rewriting the schema's enum line itself — and the model *refused both times*, returning the sensible `poetry` instead. So the live model never produced an invalid answer for me to quarantine. The 422 + quarantine path is therefore proven by unit tests in [test_llm.py](test_llm.py), where `call_model` is stubbed to return unrepairable garbage: exactly one repair retry fires, then the error surfaces as `422 {"error": ...}` and a line lands in `quarantine.jsonl`. That test also pins the other half of the contract: input validation rejects with 400 *before* any model call is made.

Two curls to test it in five seconds (server running, `LLM_STUB=1` costs nothing):

```
curl -X POST http://localhost:8000/enrich -H "Content-Type: application/json" ^
  -d "{\"title\": \"A Light in the Attic\", \"description\": \"A collection of poems and drawings.\", \"price_gbp\": 51.77}"
→ {"category":"other","summary":"Stub mode: no model was called.","quality_flags":["no_flags"],"confidence":0.0}

curl -X POST http://localhost:8000/enrich -H "Content-Type: application/json" -d "{\"description\": \"x\"}"
→ {"error":"Invalid or missing field: 'title'"}
```

The same first curl with the real model (`LLM_STUB` unset), exact response captured 2026-11-15:

```
curl -X POST http://localhost:8010/enrich -H "Content-Type: application/json" ^
  -d "{\"title\": \"A Light in the Attic\", \"description\": \"A collection of humorous poems and drawings by Shel Silverstein. First published in 1981, the book contains more than 100 poems and illustrations.\", \"price_gbp\": 51.77}"
→ {"category":"poetry","summary":"A collection of humorous poems and drawings by Shel Silverstein, first published in 1981 with more than 100 poems and illustrations.","quality_flags":["no_flags"],"confidence":0.9}
```

### Provider and configuration

Three environment variables decide everything about the model — the reason no provider should ever be hardcoded:

```
LLM_BASE_URL=https://openrouter.ai/api/v1   # OpenRouter (free lane; Ollama would be http://localhost:11434/v1/)
LLM_API_KEY=<your key, in .env, never in git>
LLM_MODEL=openrouter/free                    # a rotating router id — on 2026-11-15 it served baidu/ernie-5.5-flash-preview:free
```

Also honoured: `LLM_STUB=1` (no model call), `LLM_ENABLED=false` (kill switch → 503).

### Eval result — 6/8 (75%), 2026-11-15, prompt `enrich-v1`

Eight hand-labelled cases live in [evals/cases.json](evals/cases.json), run by `python evals/run_evals.py` against the live endpoint ([run_evals.py](evals/run_evals.py)). Six clear cases passed (Sapiens, Shakespeare's Sonnets, Aladdin, Scott Pilgrim, Mesaerion, #HigherSelfie). Two failed:

- **Libertarianism for Beginners** — expected `academic`, got `nonfiction`. Half of this is my label: "for beginners" is intro nonfiction, and `academic` arguably over-reaches. The honest reading is that this case is mis-labelled rather than mis-answered.
- **Penny Maybe** — the deliberate ambiguous case (vague title, 256-character description), expected to hit the when-unsure rule (`other`, confidence < 0.5). The model instead answered `children` confidently. This is the real miss: the when-unsure instruction was not followed, and it is the first thing prompt v2 should target.

A number you can compare is worth more than a high number: the next prompt change gets judged against 6/8.

### What one call cost

The structured log line from a real call (2026-11-15, `openrouter/free`):

```
{"ts": "2026-11-15T11:01:48+00:00", "event": "call", "attempt": 1, "duration_ms": 14826,
 "model": "openrouter/free", "prompt_version": "v1", "prompt_tokens": 837, "completion_tokens": 946}
```

1,783 tokens per call. On the free lane this costs $0.00 but is rate-capped at 50 calls/day (20/min). On a paid equivalent priced like gpt-4o-mini ($0.15/M input, $0.60/M output) that is ≈ $0.00069 per call, so **10,000 enrichments a day ≈ $7/day** — output tokens dominate (946 of 1,783), which is where a shorter enforced output would pay off.

### What I'd fix with another day

1. Prompt v2 that actually triggers the when-unsure rule (the Penny Maybe case), then re-run the eval to see whether 6/8 moves.
2. Decide honestly whether `academic` is earning its place in the closed list — the eval suggests the model will almost never pick it.
3. A cache keyed on input + prompt version: re-running enrichment over the same 60 scraped records burns the daily 50-call allowance for nothing.

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

The same full cycle also works via Swagger UI at `/docs` → [screenshot](docs/swagger-ui.png).

## Persistence — proven across a full stack restart

I created a task ("Survives compose down", id 4), then ran `docker compose down` — **both containers destroyed** — and `docker compose up` again. `GET /tasks` returned 4 tasks, including "Survives compose down". The rows live in the `taskdata` volume, outside the containers, so the database dying costs nothing.

The same holds for the app alone: restart only the `api` container, the rows are still there — the database is a separate program now; the app's death never touches the data.

The seed guard carried over from A2: 3 example tasks inserted only when `SELECT COUNT(*)` returns 0 — restart the stack three times, still 3 seed rows.

## The data, seen from inside the database

`psql` inside the db container (`docker exec <db-container> psql -U postgres -d tasks`) — `\dt` and a `SELECT`, the same rows the API serves → [screenshot](docs/db-postgres.png).

One query I ran by hand and what it returned:

```sql
SELECT * FROM tasks WHERE done;
-- id 3 | 'Write API documentation' | t   — the single completed seed task
```

## Extras

### Filtering, search & pagination — in SQL, evaluated by Postgres

```
GET /tasks?done=true         → WHERE done = TRUE
GET /tasks?search=milk      → WHERE title ILIKE '%milk%' (case-insensitive)
GET /tasks?limit=2&offset=2 → LIMIT 2 OFFSET 2
```

`ILIKE` is Postgres' case-insensitive LIKE — it preserves the A1/A2 search behaviour, which SQLite gave for free.

### Stats & reset

```
> curl http://localhost:8000/stats
{"total":3,"done":1,"open":2}        -- SELECT COUNT(*), SUM(done::int) FROM tasks

> curl -X POST http://localhost:8000/reset
{"message":"Reset to seed tasks","count":3}
```

## AI vs Me (bonus rounds)

The full stories — my self-written prompts, what the AI got right, what it silently decided, what my prompts forgot to specify, and the rematch rounds — live in **[ai-version/README.md](ai-version/README.md)**. Hand-built code stays in the repo root; AI output is quarantined in `ai-version/`.

## Repo layout

```
├── main.py           # routes only — no database line in here
├── repository.py     # ALL database access (psycopg, parameterized queries)
├── test_main.py      # 24 pytest tests covering the whole CRUD cycle
├── test_llm.py       # 18 pytest tests for the LLM plumbing (zero model calls)
├── JOB-CARD.md       # W7 job card: input, output, closed lists, "must never" rules
├── prompts/          # versioned prompt files (enrich-v1.md — the prompt is code)
├── evals/            # 8 labelled cases + the eval runner
├── requirements.txt  # pip install -r requirements.txt
├── Dockerfile        # app image (python:3.14-slim + uvicorn)
├── compose.yaml      # app + db (postgres:17, volume, healthcheck)
├── .env.example      # committed config template (.env itself is git-ignored)
├── docs/             # screenshots
└── ai-version/       # bonus — AI code in quarantine (W2 + W3 + W7 rounds)
```

## Git history = one commit per stage

Week 2 (in-memory):

```
Stage 0: hello server ... Stage 7: AI vs me   (10 commits, one per stage)
```

Week 3 · A2 (SQLite migration):

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

Week 3 · A3 (containerized Postgres):

```
Stage 0: Postgres in Docker + gitignore
Stage 1: connect via .env and create table
Stage 2: read from Postgres
Stage 3: full CRUD on Postgres
Tests: adapt test suite to Postgres storage
Stage 4: docker-compose the whole stack
Stage 5: one-command stack + docs
Stage 6: AI vs me (AI rematch)
```

Week 7 · A17 "Put an LLM behind your API" (the portal lists this as Week 6, "Connect to an AI API"):

```
Stage 0: job card, provider working, key in .env
Stage 1: endpoint, input validation, output schema, stub mode
Stage 2: prompt v1 as a versioned file, wired to the endpoint
Stage 3: parse, validate, repair once, quarantine on failure
Stage 4: timeout, retry policy, cost logging, kill switch
Stage 5: eval set, results, README, published
Bonus: AI vs me
```

## The idea worth keeping

APIs describe what an application does. Databases describe where it stores its data. This repo is that sentence, proven three times: the same 24 tests passed against a Python list, against a SQLite file, and against a containerized Postgres server. Storage is an implementation detail — and once the app and its database both run in containers, "it works on my machine" quietly becomes "it works on every machine."
