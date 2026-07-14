<div align="center">

# ⚖️ LegalEase AI

**Turn dense legal contracts into plain-English answers — in seconds.**

An AI-powered document intelligence platform that summarizes contracts, flags risky clauses, and answers natural-language questions with citations — built on a production-style FastAPI backend and a Next.js frontend.

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vertex AI](https://img.shields.io/badge/Vertex%20AI-Gemini-4285F4?style=flat-square&logo=googlecloud&logoColor=white)](https://cloud.google.com/vertex-ai)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white)](.github/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Prototype-lightgrey?style=flat-square)](#-license)

[Features](#-features) • [Architecture](#-architecture) • [Getting Started](#-getting-started) • [API Reference](#-api-reference) • [Deployment](#-deployment)

</div>

---

## 📌 Overview

Reading a legal contract shouldn't require a law degree. **LegalEase AI** lets anyone upload a PDF contract and instantly get:

- A **plain-English summary** — for both lawyers and laypeople
- A **risk report** that flags clauses by severity (Low / Medium / High)
- An **interactive Q&A** assistant that answers questions about the document with source citations

The project is built like a real product, not a notebook demo: typed API contracts, request validation, caching, rate limiting, Prometheus metrics, Dockerized deployment, and CI on every push.

---

## ✨ Features

| | |
|---|---|
| 📄 **Smart Summarization** | Chunked summarization pipeline handles documents of any length, producing lawyer-ready bullet points plus an "explain it like I'm 15" version. |
| ⚠️ **Risk Detection** | LLM-driven clause analysis returns structured, validated JSON — every clause tagged `LOW` / `MEDIUM` / `HIGH` with a plain-language reason. |
| 💬 **Contextual Q&A** | Keyword-ranked retrieval over document chunks feeds the model relevant context and returns answers with citation snippets. |
| 🔍 **OCR Fallback** | Scanned, non-text PDFs are automatically routed through Tesseract OCR when enabled. |
| 🚀 **Production Hardening** | SHA-256 response caching, per-IP rate limiting, upload size limits, and structured error handling. |
| 📊 **Observability** | Built-in `/metrics` endpoint (Prometheus) tracks request counts, errors, and latency per route. |
| 🐳 **Containerized** | Backend ships with a slim Docker image, ready for Cloud Run or any container platform. |
| ✅ **CI Pipeline** | GitHub Actions builds the frontend and validates the backend on every push and PR. |

---

## 🏗 Architecture

```
          ┌─────────────────────────┐
          │       Next.js UI        │
          │   (Summarize / Risks    │
          │       / Q&A tabs)       │
          └─────────────────────────┘
                       │  REST (multipart/form-data)
                       ▼
          ┌─────────────────────────┐
          │     FastAPI Backend     │
          │     ───────────────     │
          │  • PDF text extraction  │
          │     • OCR fallback      │
          │       • Chunking        │
          │ • Caching / rate limit  │
          │  • Prometheus metrics   │
          └─────────────────────────┘
                       │
                       ▼
          ┌─────────────────────────┐
          │   Vertex AI (Gemini)    │
          │   with model fallback   │
          │  chain for resilience   │
          └─────────────────────────┘
```

**Design highlights:**
- **Resilient LLM calls** — the client walks a fallback chain across multiple Gemini model versions so a single model outage never breaks the app.
- **Chunked summarization** — long contracts are split, summarized in parallel sections, then recombined into one coherent summary.
- **Grounded Q&A** — answers are generated only from the most relevant chunks (keyword-overlap ranking) and returned alongside the exact snippets used, so answers stay traceable to the source document.

---

## 🧰 Tech Stack

**Backend:** FastAPI · Pydantic · PyPDF2 · Vertex AI (Gemini) · Prometheus Client · Uvicorn
**Frontend:** Next.js 14 (App Router) · React 18 · TypeScript · Tailwind CSS · Recharts · react-pdf
**Infra/Tooling:** Docker · GitHub Actions · Google Cloud Run

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+
- A Google Cloud project with the Vertex AI API enabled

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Authenticate (recommended — no key file needed)
gcloud auth application-default login

export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"
export VERTEX_MODEL="gemini-2.0-flash-001"
export FRONTEND_ORIGIN="http://localhost:3000"

uvicorn main:app --reload --port 8000
```

The API is now live at `http://localhost:8000` — interactive docs at `http://localhost:8000/docs`.

### 2. Frontend

```bash
cd frontend
npm install
export NEXT_PUBLIC_API_BASE="http://localhost:8000"
npm run dev
```

Open `http://localhost:3000` and upload a contract to try Summarize, Risks, and Q&A.

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | Prometheus metrics |
| `POST` | `/summarize` | Upload a PDF (`file`) → returns bullet-point + ELI15 summary |
| `POST` | `/risks` | Upload a PDF (`file`) → returns structured risk clauses with severity |
| `POST` | `/qa` | Upload a PDF (`file`) + a `question` → returns an answer with citation snippets |

**Example:**
```bash
curl -F "file=@contract.pdf" http://localhost:8000/summarize
curl -F "file=@contract.pdf" http://localhost:8000/risks
curl -F "file=@contract.pdf" -F "question=What is the termination clause?" http://localhost:8000/qa
```

---

## ☁️ Deployment

The backend is designed for zero-secret-file deployment on **Google Cloud Run**, using a service account identity instead of a mounted JSON key:

```bash
gcloud builds submit backend --tag REGION-docker.pkg.dev/PROJECT/REPO/legal-backend:latest

gcloud run deploy legal-backend \
  --image REGION-docker.pkg.dev/PROJECT/REPO/legal-backend:latest \
  --region REGION \
  --allow-unauthenticated \
  --port 8000 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=PROJECT,GOOGLE_CLOUD_LOCATION=REGION,VERTEX_MODEL=gemini-2.0-flash-001
```

Configurable via environment variables: `MAX_PDF_MB`, `RATE_LIMIT_PER_MIN`, `OCR_ENABLED`, `CORS_ORIGINS`, `LOG_LEVEL`.

---

## 📁 Project Structure

```
Legal-Ease-AI/
├── backend/            # FastAPI service
│   ├── main.py           # Routes, validation, caching, rate limiting
│   ├── llm_client.py      # Vertex AI Gemini client with model fallback
│   ├── prompts.py         # Prompt templates for summarize/risks/Q&A
│   └── Dockerfile
├── frontend/           # Next.js + Tailwind UI
│   ├── app/               # Summarize / Risks / Q&A pages
│   ├── components/        # Reusable UI (upload, PDF viewer, alerts)
│   └── lib/api.ts          # Typed API client
├── docs/               # Notes and deployment guides
└── .github/workflows/  # CI pipeline
```

---

## 🗺 Roadmap

- [ ] Vector-embedding retrieval for Q&A (replacing keyword-overlap ranking)
- [ ] Multi-document comparison view
- [ ] User accounts and document history
- [ ] Support for DOCX and scanned-image uploads by default

---

## 📄 License

This project is a prototype built for demonstration and learning purposes.

---

<div align="center">
Built with FastAPI, Next.js, and Vertex AI Gemini.
</div>
