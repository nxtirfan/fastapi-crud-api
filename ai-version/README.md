# AI vs Me — Stage 7: The AI Rematch

Versi API ini dibuat oleh AI (saya tulis prompt-nya sendiri, tanpa menyalin teks
assignment) dan disimpan terpisah di folder `ai-version/` agar versi tulisan
tangan di `../main.py` tetap murni hasil kerja manual.

Menjalankan versi AI (port berbeda agar bisa dibandingkan berdampingan):

```bash
cd ai-version
pip install fastapi uvicorn
python -m uvicorn main:app --port 8001
```

## Prompt yang saya tulis (Round 1)

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

## Apa yang terjadi (hasil karantina)

- **Jalankan pertama:** server langsung start tanpa error di percobaan pertama.
- **Checkpoint Stage 4 (`curl -i`):**
  - GET /tasks → 200 PASS
  - GET /tasks/1 → 200 PASS · GET /tasks/99 → 404 PASS, tapi format error
    `{"detail": "..."}` (default FastAPI), bukan `{"error": "..."}` — FAIL
  - POST valid → 201 PASS · POST `{}` → **422**, bukan 400 — FAIL
  - PUT valid → 200 PASS · PUT `{}` → 422, bukan 400 — FAIL
  - DELETE → 204 PASS · DELETE unknown → 404 PASS

## Tiga perbedaan konkret (diff `git diff --no-index ../main.py main.py`)

### 1. Apa yang AI lakukan lebih baik — dan mengapa bisa saya jelaskan

AI memakai helper `find_task()` berbasis `next(... for ...)` (generator
expression) sekali untuk dipakai di GET/PUT/DELETE, sementara versi saya
menulis loop `for ... if task["id"] == task_id` tiga kali di tiga endpoint.
Fungsinya sama persis — `next()` mengembalikan elemen pertama yang cocok atau
`None` — tetapi versi AI lebih DRY. Saya sudah mengadopsi pola ini di kode
utama saya (lihat `find_task()` di `main.py` saya).

### 2. Apa yang AI salah lakukan / diam-diam abaikan dari prompt

Saya eksplisit minta "missing or empty title returns 400" dan "every error
must be JSON with an error key", tetapi AI membiarkan FastAPI memakai
`RequestValidationError` bawaan (422, key `"detail"`) — dua pelanggaran
sekaligus terhadap prompt yang sudah jelas. Penyebabnya: AI mendefinisikan
`title: str` sebagai field wajib di Pydantic model, sehingga validasi
terjadi sebelum handler saya sempat jalan, dan AI tidak menulis exception
handler untuk mengubahnya. Pelajarannya: AI memenuhi *huruf* endpoint
sekaligus mengabaikan *isi* aturan status code.

### 3. Apa yang prompt saya lupa tentukan — dan AI putuskan sendiri

Prompt saya tidak menyebut: bentuk response error 422 vs 400 itu *harus*
diganti lewat custom exception handler, tidak menyebut nama API dan versi,
tidak menyebut tag di Swagger, dan tidak menyebut struktur GET / harus
menampung semua endpoint publik. AI lalu memutuskan sendiri judul API
("Todo API"), mengembalikan list `"detail"` bergaya validasi, dan hanya
menulis `/tasks` di GET /. Semua keputusan itu masuk akal tapi bukan milik
saya — spesifikasi yang kurang lengkap selalu diisi AI dengan pilihan
paling umum, yang belum tentu pilihan saya.

## Rematch — prompt yang diperbaiki (Round 2)

> (Tidak menyalin teks assignment — tulisan saya sendiri, diperbaiki dari
> kesalahan Round 1 di atas.)
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

**Apa yang berubah (satu kalimat):** Dengan menyebut format error secara
eksplisit, melarang 422/`detail` langsung, dan memerintahkan exception
handler + field Optional, AI Round 2 langsung menghasilkan 400 dengan
`{"error": ...}` di semua kasus yang Round 1 gagali — kode AI sekarang lolos
100% checkpoint Stage 4 saya.

## Kesimpulan

Kualitas output AI persis sebesar kualitas spesifikasi saya — dan saya hanya
bisa menilainya karena sudah membangun API ini dengan tangan sendiri
sebelumnya.
