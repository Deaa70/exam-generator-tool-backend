# Exam Generator — Backend

FastAPI service that turns exam metadata + questions (with optional images and LaTeX math) into a ready-to-print **A4 PDF**.

The client posts a multipart form containing the exam header (name, year, class level, subject, time, marks, teacher) and an indexed list of questions. Each question can include an HTML/LaTeX body and an optional image. The server renders the questions into an HTML template, typesets the math with MathJax in a headless Chromium instance, and streams the resulting PDF back to the caller.

---

## Features

- **Multipart upload** of exam metadata + questions + per-question images.
- **LaTeX → PDF** via MathJax 3 (inline-only normalization; block constructs are rewritten).
- **Arabic-first template** (`dir="rtl"`, Naskh-styled typography) with a three-column header.
- **Headless Chromium rendering** (Playwright) with a strict "MathJax must succeed" guard — the service refuses to emit a broken PDF.
- **"انتهى" pinned to the bottom of the last page** so the printed exam always ends on a full page.
- **Per-IP rate limiting** (in-memory, sliding window).
- **SQLite-backed stats** (`/stats`) tracking number of generations and total questions generated.
- **CORS restricted** to the production frontend origin (`https://exam-generator.siraj.sy`) via the `ALLOWED_ORIGINS` env var.

---

## Tech Stack

| Layer            | Tool                                       |
| ---------------- | ------------------------------------------ |
| Web framework    | FastAPI + Uvicorn (standard)               |
| Form parsing     | `python-multipart`                         |
| Math rendering   | MathJax 3.2.2 (loaded from CDN)            |
| HTML → PDF       | Playwright (headless Chromium)             |
| Persistence      | SQLite (`exams.db`)                        |
| Configuration    | `python-dotenv` (`.env` support)           |

> **Note:** the current `requirements.txt` is missing `playwright`. Add it (see below) before installing.

---

## Project Structure

```
app/
├── __init__.py           # Loads .env before other modules read settings
├── main.py               # FastAPI app, /generate and /stats endpoints
├── exam_html.py          # LaTeX normalizer + HTML template builder
├── pdf_render.py         # Playwright: HTML → PDF
├── database.py           # SQLite helpers (init_db, record_generation, get_stats)
├── rate_limiter.py       # In-memory per-IP sliding-window limiter
└── template.html         # HTML/CSS shell used by the PDF renderer
```

---

## Requirements

- **Python 3.11+** (uses `DROP COLUMN`-friendly SQLite and modern async idioms)
- **Playwright Chromium** browser binary installed locally
- Network access to `cdn.jsdelivr.net` (MathJax is fetched at render time)

---

## Installation

```bash
# 1. Clone
git clone <repo-url>
cd exam-backend

# 2. Create & activate a virtual environment (uv recommended)
uv venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# 3. Install Python dependencies
uv pip install -r requirements.txt
uv pip install playwright          # missing from requirements.txt

# 4. Install the Chromium browser binary used by Playwright
playwright install chromium
```

Or, if you prefer pip:

```bash
pip install -r requirements.txt
pip install playwright
playwright install chromium
```

---

## Configuration

Create a `.env` file next to `app/` (it is loaded automatically by `app/__init__.py`):

```env
# Rate limiting
RATE_LIMIT_REQUESTS=5
RATE_LIMIT_WINDOW_SECONDS=300

# CORS — comma-separated list of origins allowed to call this API.
# Production: your domain only. Add localhost entries for local dev.
ALLOWED_ORIGINS=https://exam-generator.siraj.sy
```

| Variable                    | Default                                 | Description                                          |
| --------------------------- | --------------------------------------- | ---------------------------------------------------- |
| `RATE_LIMIT_REQUESTS`       | `5`                                     | Max requests allowed per IP inside the window.       |
| `RATE_LIMIT_WINDOW_SECONDS` | `300`                                   | Sliding window length, in seconds.                   |
| `ALLOWED_ORIGINS`           | `https://exam-generator.siraj.sy`       | Comma-separated list of CORS-allowed origins.        |

For local development, add the frontend dev origin:

```env
ALLOWED_ORIGINS=https://exam-generator.siraj.sy,http://localhost:3000,http://127.0.0.1:3000
```

> The SQLite file path is currently hard-coded as `DB_PATH = "exams.db"` in `database.py`. It is **relative to the working directory** where the server is started.

---

## Running the Server

```bash
# Inside app/
uv run fastapi dev
```

The dev server starts at `http://127.0.0.1:8000` and reloads on file changes.

For production:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Interactive API docs: `http://127.0.0.1:8000/docs`.

---

## API

### `GET /`

Health check. Returns `{"service": "exam-generator", "docs": "/docs"}`.

### `POST /generate`

Generates and returns a PDF.

**Content-Type:** `multipart/form-data`

**Top-level form fields** (all required):

| Field          | Type    | Example       |
| -------------- | ------- | ------------- |
| `name`         | string  | `امتحان الرياضيات` |
| `year`         | string  | `2025`        |
| `class_level`  | string  | `الثاني عشر`   |
| `subject_name` | string  | `الرياضيات`    |
| `time`         | string  | `ساعتان`      |
| `marks`        | integer | `100`         |
| `teacher_name` | string  | `أ. محمد`      |

**Question fields** (indexed; at least one required):

```
questions[0][text]   = "<p>...</p>"       # HTML + LaTeX (inline)
questions[0][image]  = <uploaded file>    # optional
questions[1][text]   = "..."
questions[1][image]  = <uploaded file>
...
```

Both `questions[0][text]` and `questions[0].text` syntaxes are accepted.

**Response:** `200 OK`

- Body: PDF bytes
- Headers: `Content-Disposition: attachment; filename*=UTF-8''<name>.pdf`

**Errors:**

| Status | When                                                                |
| ------ | ------------------------------------------------------------------- |
| `400`  | No questions found in the form.                                     |
| `429`  | Rate limit exceeded for the client IP.                              |
| `502`  | PDF rendering failed (e.g. MathJax CDN unreachable).                 |

**Example with cURL:**

```bash
curl -X POST http://127.0.0.1:8000/generate \
  -F 'name=امتحان الرياضيات' \
  -F 'year=2025' \
  -F 'class_level=الثاني عشر' \
  -F 'subject_name=الرياضيات' \
  -F 'time=ساعتان' \
  -F 'marks=100' \
  -F 'teacher_name=أ. محمد' \
  -F 'questions[0][text]=ما هو ناتج $2+2$؟' \
  -F 'questions[1][text]=أوجد قيمة $x$ في $x^2 = 9$' \
  --output exam.pdf
```

### `GET /stats`

Returns cumulative generation counters.

```json
{ "generations": 42, "total_questions": 320 }
```

---

## How It Works

1. **Form parsing** — `parse_questions_form` walks `form.multi_items()` and matches keys against `^questions\[(\d+)\][.\[](text|image)\]?$`. Questions are returned in index order.
2. **Image handling** — each uploaded image is read into bytes; the MIME type is used to pick the file extension (`.png`, `.jpg`, `.gif`, `.webp`, `.svg`).
3. **HTML build** — `render_exam_html` fills `template.html` with the header (three columns: `side_start`, `header-center`, `side_end`) and the question list. Question text passes through `normalize_latex` first, which:
   - Converts `$$...$$` → `$...$`
   - Converts `\[...\]` → `\(...\)`
   - Rewrites `\begin{align}...\end{align}` → `$\begin{aligned}...\end{aligned}$`
   - Strips `\label{...}`
   - Collapses internal whitespace (inline math cannot contain line breaks)
4. **PDF rendering** — Playwright opens the HTML on its own private event loop (Windows Proactor loop workaround), waits for `window.__DOCUMENT_READY__` and the `__MATHJAX_OK__` flag, pins the "انتهى" mark to the last page, then calls `page.pdf(...)` with A4 geometry.
5. **Response** — the PDF bytes are streamed back with a `Content-Disposition` header using RFC 5987 encoding for the Arabic filename.
6. **Stats** — `record_generation(n)` inserts one row per request; `get_stats()` aggregates.

---

## LaTeX Normalization Rules

Everything is treated as **inline math** for print reliability. The following rewrites happen inside `normalize_latex`:

| Input                                        | Output                                     |
| -------------------------------------------- | ------------------------------------------ |
| `$$x^2 + 1$$`                                | `$x^2 + 1$`                                |
| `\[ x^2 + 1 \]`                              | `\(x^2 + 1\)`                              |
| `\begin{align} a &= b \\ c &= d \end{align}` | `$\begin{aligned} a &= b \\ c &= d \end{aligned}$` |
| `\begin{equation} ... \end{equation}`        | `$ ... $`                                  |
| `\label{eq:1}`                               | *(removed)*                                |

The MathJax config in `exam_html.py` supports both `$...$` and `\(...\)` delimiters, but the normalizer guarantees only those two forms reach the page.

---

## CORS

The API only accepts requests from origins listed in `ALLOWED_ORIGINS`. The default is `https://exam-generator.siraj.sy`, so in production only your frontend domain can call the API.

Origins are matched **literally** — no wildcard subdomains. If you serve the frontend from both `https://exam-generator.siraj.sy` and `https://www.exam-generator.siraj.sy`, list both:

```env
ALLOWED_ORIGINS=https://exam-generator.siraj.sy,https://www.exam-generator.siraj.sy
```

`allow_credentials` is `False` because the API doesn't use cookies or auth headers. If you later add cookie-based auth, set it to `True` and make sure `ALLOWED_ORIGINS` no longer contains `*`.

---

## Database

`exams.db` is created automatically on startup if missing.

```sql
CREATE TABLE IF NOT EXISTS generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    num_questions INTEGER NOT NULL
);
```

> **Schema changes:** `init_db` uses `CREATE TABLE IF NOT EXISTS`, so if an older version of the table exists with extra columns, it will *not* be migrated automatically. Delete `exams.db` (dev) or run an `ALTER TABLE` migration if you change the shape.

---

## Rate Limiting

`rate_limiter.py` keeps a `dict[str, list[float]]` of timestamps per client IP. It is **in-memory** and **not shared between workers**. For multi-worker or multi-instance deployments, replace it with Redis or a similar shared store.

Client IP is taken from `request.client.host`, which will be the proxy IP unless `--proxy-headers` is enabled on Uvicorn.

---

## Development Notes

- **Windows + Playwright:** `_render_pdf_blocking` uses `asyncio.ProactorEventLoop` on Windows. On other platforms it uses a fresh default loop. This is required because uvicorn's running loop and Playwright's subprocess transport don't always cooperate on Windows.
- **CORS:** the API only accepts requests from origins listed in `ALLOWED_ORIGINS`. To test the frontend locally, either add `http://localhost:3000` to that env var or run with `ALLOWED_ORIGINS=https://exam-generator.siraj.sy,http://localhost:3000`. If you change the frontend domain later, update this variable and restart the server.
- **MathJax CDN dependency:** every PDF render fetches MathJax from `cdn.jsdelivr.net`. If the machine has no outbound network access, the endpoint returns `502`. To make the service fully offline, vendor `tex-mml-chtml.js` into `app/static/` and change `MATHJAX_BLOCK` in `exam_html.py` to a relative path.
- **Template customization:** `template.html` is loaded as a `string.Template` — placeholders are `${html_title}`, `${mathjax_block}`, `${ready_script}`, `${exam_name}`, `${exam_year}`, `${side_start}`, `${side_end}`, `${questions_html}`. Add new placeholders by extending `render_exam_html`.

---

## Troubleshooting

**`sqlite3.IntegrityError: NOT NULL constraint failed: generations.topic`**
A stale `exams.db` from an older schema. Delete the file (`Remove-Item exams.db` on Windows, `rm exams.db` on Unix) and restart — `init_db` will recreate it.

**`uv trampoline failed to canonicalize script path` (Windows)**
Move the project out of paths with spaces, delete `.venv`, and recreate it with `uv venv`. Update uv (`uv self update`) — 0.9.9+ stores trampoline metadata in `.rcdata` instead of `%TEMP%`, avoiding Defender interference.

**`MathJax failed to load or render (CDN unreachable?)`**
Either the machine has no internet access, or the CDN is blocked. Vendor MathJax locally (see *Development Notes*).

**Browser console shows a CORS error**
The origin sending the request is not in `ALLOWED_ORIGINS`. Check the exact scheme, host, and port of the frontend URL, add it to the env var (comma-separated), and restart the server. Origins are matched literally — `http://` and `https://` are different, `www.` and bare domain are different.

**PDF renders but math looks unstyled**
Verify `window.__MATHJAX_OK__` was `true` — the guard in `pdf_render.py` will raise before writing the PDF if not. If you're testing a variant that skips the guard, make sure MathJax's startup promise actually resolved.

---

## License

Add your license here.