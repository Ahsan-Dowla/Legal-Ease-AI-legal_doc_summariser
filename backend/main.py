import os
import re
import io
import time
import json
import hashlib
import logging
from typing import List, Literal, Tuple, Optional

from fastapi import FastAPI, UploadFile, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from PyPDF2 import PdfReader
from dotenv import load_dotenv
from prometheus_client import Counter, Histogram, CONTENT_TYPE_LATEST, generate_latest

from llm_client import chat
from prompts import (
    summary_prompt,
    risks_prompt,
    qa_prompt,
    combine_summaries_prompt,
    qa_prompt_with_context,
)

load_dotenv()

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("legalease")

app = FastAPI(title="LegalEase AI Backend")

# CORS configuration
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
extra_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
allowed_origins = sorted(set([frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"] + extra_origins))
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://legal-ease-ai-legal-doc-summariser.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config
MAX_PDF_MB = int(os.getenv("MAX_PDF_MB", "10"))
OCR_ENABLED = os.getenv("OCR_ENABLED", "false").lower() == "true"
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))

# Metrics
REQUEST_COUNTER = Counter("le_requests_total", "Total requests", ["endpoint"])
ERROR_COUNTER = Counter("le_errors_total", "Total errors", ["endpoint"])
DURATION_HIST = Histogram("le_request_duration_seconds", "Request duration (s)", ["endpoint"])

# Caches and rate-limiter
summarize_cache: dict[str, str] = {}
risks_cache: dict[str, List[dict]] = {}
qa_cache: dict[Tuple[str, str], dict] = {}
rate_buckets: dict[str, Tuple[int, float]] = {}  # ip -> (count, window_start)


class SummaryResponse(BaseModel):
    summary: str = Field(..., description="Concise bullet points and an ELI15 explanation")


class RiskItem(BaseModel):
    clause: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    reason: str


class RisksResponse(BaseModel):
    risks: List[RiskItem]


class Citation(BaseModel):
    chunk: int
    snippet: str


class QAResponse(BaseModel):
    answer: str
    citations: Optional[List[Citation]] = None


def _read_all(file: UploadFile) -> bytes:
    file.file.seek(0)
    data = file.file.read()
    file.file.seek(0)
    return data


def _validate_pdf(file: UploadFile, data: bytes):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are supported")
    ct = (file.content_type or "").lower()
    if "pdf" not in ct:
        # allow if extension ok but content-type missing from some browsers
        logger.warning("Non-PDF content-type: %s", ct)
    max_bytes = MAX_PDF_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"PDF exceeds size limit of {MAX_PDF_MB} MB")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(page.extract_text() or "" for page in reader.pages)
        if text and text.strip():
            return text
        if OCR_ENABLED:
            return _ocr_pdf_bytes(pdf_bytes)
        raise ValueError("No text found in PDF; enable OCR to extract from scanned PDFs")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read PDF: {e}")


def _ocr_pdf_bytes(pdf_bytes: bytes) -> str:
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except Exception as e:  # pragma: no cover
        logger.exception("OCR requested but dependencies not installed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="OCR not available. Install Tesseract and python packages (pdf2image, pillow, pytesseract).",
        )
    images = convert_from_bytes(pdf_bytes, dpi=200)
    text = "\n".join(pytesseract.image_to_string(img) for img in images)
    if not text.strip():
        raise HTTPException(status_code=400, detail="OCR did not extract any text")
    return text


def chunk_text(text: str, max_chars: int = 3000) -> List[str]:
    words = text.split()
    chunks: List[str] = []
    current: List[str] = []
    length = 0
    for w in words:
        new_len = length + len(w) + (1 if length else 0)
        if new_len > max_chars and current:
            chunks.append(" ".join(current))
            current = [w]
            length = len(w)
        else:
            current.append(w)
            length = new_len
    if current:
        chunks.append(" ".join(current))
    return chunks


def clean_json_array(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.IGNORECASE | re.DOTALL)
    start = s.find("[")
    end = s.rfind("]")
    if start != -1 and end != -1 and end > start:
        return s[start : end + 1]
    return s


def _check_rate_limit(ip: str):
    now = time.time()
    count, start = rate_buckets.get(ip, (0, now))
    if now - start >= 60:
        rate_buckets[ip] = (1, now)
        return
    if count + 1 > RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")
    rate_buckets[ip] = (count + 1, start)


@app.get("/")
def root():
    return {"name": "LegalEase AI Backend", "docs": "/docs", "health": "/health"}


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/summarize", response_model=SummaryResponse)
async def summarize(request: Request, file: UploadFile):
    endpoint = "summarize"
    REQUEST_COUNTER.labels(endpoint).inc()
    start = time.perf_counter()
    try:
        _check_rate_limit(request.client.host if request.client else "?")
        data = _read_all(file)
        _validate_pdf(file, data)
        file_key = _sha256(data)
        if file_key in summarize_cache:
            return {"summary": summarize_cache[file_key]}
        text = extract_text_from_pdf_bytes(data)
        chunks = chunk_text(text, max_chars=3000)
        if len(chunks) == 1:
            summary = chat(summary_prompt(chunks[0]))
        else:
            partials = [chat(summary_prompt(c)) for c in chunks]
            summary = chat(combine_summaries_prompt(partials))
        summarize_cache[file_key] = summary
        return {"summary": summary}
    except Exception:
        ERROR_COUNTER.labels(endpoint).inc()
        raise
    finally:
        DURATION_HIST.labels(endpoint).observe(time.perf_counter() - start)


@app.post("/risks", response_model=RisksResponse)
async def risks(request: Request, file: UploadFile):
    endpoint = "risks"
    REQUEST_COUNTER.labels(endpoint).inc()
    start = time.perf_counter()
    try:
        _check_rate_limit(request.client.host if request.client else "?")
        data = _read_all(file)
        _validate_pdf(file, data)
        file_key = _sha256(data)
        if file_key in risks_cache:
            return {"risks": risks_cache[file_key]}
        text = extract_text_from_pdf_bytes(data)
        raw = chat(risks_prompt(text), system="Only output valid JSON.")
        candidate = clean_json_array(raw)
        try:
            data_json = json.loads(candidate)
            if not isinstance(data_json, list):
                raise ValueError("Expected a list of risks")
        except Exception:
            data_json = [{
                "clause": "Parsing error",
                "risk_level": "LOW",
                "reason": "Could not parse AI output",
            }]

        normalized: List[dict] = []
        for item in data_json[:100]:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("risk_level"), str):
                item["risk_level"] = item["risk_level"].upper()
            try:
                normalized.append(RiskItem(**item).model_dump())
            except Exception:
                continue
        if not normalized:
            normalized = [{
                "clause": "No risks found or parsing failed",
                "risk_level": "LOW",
                "reason": "Fallback result",
            }]
        risks_cache[file_key] = normalized
        return {"risks": normalized}
    except Exception:
        ERROR_COUNTER.labels(endpoint).inc()
        raise
    finally:
        DURATION_HIST.labels(endpoint).observe(time.perf_counter() - start)


@app.post("/qa", response_model=QAResponse)
async def qa(request: Request, file: UploadFile, question: str = Form(...)):
    endpoint = "qa"
    REQUEST_COUNTER.labels(endpoint).inc()
    start = time.perf_counter()
    try:
        _check_rate_limit(request.client.host if request.client else "?")
        data = _read_all(file)
        _validate_pdf(file, data)
        key = (_sha256(data), question.strip())
        if key in qa_cache:
            return qa_cache[key]
        text = extract_text_from_pdf_bytes(data)
        chunks = chunk_text(text, max_chars=1500)

        # Simple retrieval scoring (keyword overlap). If you set VERTEX_EMBED_MODEL, you can
        # update llm_client to use embeddings and cosine similarity instead.
        q_words = [w.lower() for w in re.findall(r"\w+", question)]
        def score_chunk(c: str) -> int:
            c_low = c.lower()
            return sum(c_low.count(w) for w in q_words) or 0

        ranked = sorted(((i, c, score_chunk(c)) for i, c in enumerate(chunks)), key=lambda x: x[2], reverse=True)
        top = ranked[: min(5, len(ranked))]
        contexts = [(i, c[:800]) for i, c, _ in top]

        answer = chat(qa_prompt_with_context(contexts, question))
        citations = [{"chunk": i, "snippet": s} for i, s in contexts]
        result = {"answer": answer, "citations": citations}
        qa_cache[key] = result
        return result
    except Exception:
        ERROR_COUNTER.labels(endpoint).inc()
        raise
    finally:
        DURATION_HIST.labels(endpoint).observe(time.perf_counter() - start)

# Run using: uvicorn backend.main:app --reload
