import html
import logging
import os
import re
import tempfile
import uuid
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

# 1) import line
from .database import get_stats, init_db, record_generation
from .exam_html import parse_question_file, render_exam_html
from .pdf_render import render_pdf
from .rate_limiter import check_rate_limit

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("exam-generator")

RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "5"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "300"))

# Matches the multipart keys the React client sends for the questions array:
#   questions[0][text]   (or questions[0].text)   -> question text
#   questions[0][image]  (or questions[0].image)  -> the uploaded image file
QUESTION_KEY = re.compile(r"^questions\[(\d+)\](?:\.|\[)(text|image)\]?$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Exam Generator", lifespan=lifespan)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # fine here: no cookies/credentials are used
    allow_methods=["*"],
    allow_headers=["*"],
)


def enforce_rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(ip, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS):
        log.info("rate limit hit for %s", ip)
        raise HTTPException(status_code=429, detail="Rate limit exceeded, please try again later.")


def pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


def parse_questions_form(form) -> list[dict]:
    """Collect the questions from the multipart form.

    Expected keys (brackets or dots — both work):
        questions[0][text] = "..."          plain string (HTML + LaTeX)
        questions[0][image] = <file>        the uploaded image itself
    Returns [{"text": str, "image_file": UploadFile | None}, ...] in index order.
    """
    found: dict[int, dict] = {}
    for key, value in form.multi_items():
        match = QUESTION_KEY.match(key)
        if not match:
            continue
        index, field = int(match.group(1)), match.group(2)
        question = found.setdefault(index, {"text": "", "image_file": None})
        if field == "text":
            question["text"] = value
        elif hasattr(value, "read"):  # an uploaded file, not a text value
            question["image_file"] = value
    return [found[i] for i in sorted(found)]


# Extension used when saving each uploaded image, based on its content type.
MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}


async def build_pdf(exam: dict, questions: list[dict]) -> bytes:
    """1) save uploaded images into the temp dir
       2) fill template.html -> exam_<uuid>.html (images referenced by filename)
       3) render with headless Chromium -> exam_<uuid>.pdf
       4) return the PDF bytes (temp dir removes everything afterwards)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        uid = uuid.uuid4().hex[:8]
        html_path = os.path.join(tmp_dir, f"exam_{uid}.html")
        pdf_path = os.path.join(tmp_dir, f"exam_{uid}.pdf")

        # Save each question's image as a file NEXT TO the HTML file.
        for n, q in enumerate(questions):
            if q.get("image_bytes"):
                ext = MIME_EXTENSIONS.get(q.get("mime_type") or "", ".png")
                image_name = f"img_{n}{ext}"
                with open(os.path.join(tmp_dir, image_name), "wb") as f:
                    f.write(q["image_bytes"])
                q["image_path"] = image_name
            else:
                q["image_path"] = None

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(render_exam_html(exam, questions))

        try:
            await render_pdf(html_path, pdf_path)
        except Exception as e:
            log.error("PDF rendering failed: %s", e)
            raise HTTPException(status_code=502, detail=f"PDF rendering failed: {e}")

        with open(pdf_path, "rb") as f:
            return f.read()


@app.get("/")
def root():
    return {"service": "exam-generator", "docs": "/docs"}


@app.post("/generate")
async def generate(
    request: Request,
    name: str = Form(...),
    year: str = Form(...),
    class_level: str = Form(...),
    subject_name: str = Form(...),
    time: str = Form(...),           # free text now, e.g. "ساعتان"
    marks: int = Form(...),
    teacher_name: str = Form(...),
):
    enforce_rate_limit(request)

    # questions arrive as indexed form fields, each image being a real file
    raw_questions = parse_questions_form(await request.form())
    if not raw_questions:
        raise HTTPException(
            status_code=400,
            detail="No questions found. Send them as form fields: "
                   'questions[0][text]="..." and questions[0][image]=<file>',
        )

    # Read each image file to bytes (they are written to disk in build_pdf).
    question_dicts = []
    for q in raw_questions:
        image_bytes = None
        mime_type = None
        if q["image_file"] is not None:
            image_bytes = await q["image_file"].read()
            mime_type = q["image_file"].content_type or "image/png"
        question_dicts.append(
            {"text": q["text"], "image_bytes": image_bytes, "mime_type": mime_type}
        )

    exam = {
        "name": name,
        "year": year,
        "class_level": class_level,
        "subject_name": subject_name,
        "time": time,
        "marks": marks,
        "teacher_name": teacher_name,
    }

    pdf_bytes = await build_pdf(exam, question_dicts)
    record_generation(len(question_dicts))
    log.info("generated exam %r with %d questions", name, len(question_dicts))

    return pdf_response(pdf_bytes, f"{name}.pdf")


 

# 4) the stats endpoint
@app.get("/stats")
def stats():
    return get_stats()