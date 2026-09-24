# MVP Architecture

---

## System Overview

```
┌─────────────────────────────────┐
│           Browser               │
│         React Web App           │
└────────────────┬────────────────┘
                 │ HTTP / REST
                 ▼
┌─────────────────────────────────┐
│           FastAPI               │
│                                 │
│  Documents  │  Query  │  Auth   │
└──┬──────────┴────┬────┴────┬────┘
   │               │         │
   ▼               ▼         ▼
┌────────────┐ ┌──────────────────────────┐ ┌─────────┐
│ PostgreSQL │ │        Retrieval          │ │  Redis  │
│            │ │                          │ │         │
│ documents  │ │  Permission Filter       │ │  job    │
│ versions   │ │  Version Filter          │ │  queue  │
│ chunks     │ │  Vector Search(pgvector) │ └────┬────┘
│ perms      │ │  Full-Text Search        │      │
│ audit      │ │  Ranking                 │      ▼
└────────────┘ └──────────┬───────────────┘ ┌─────────┐
                          │                 │ Worker  │
                ┌─────────▼──────────┐      │ Process │
                │      OpenAI        │      └─────────┘
                │       (LLM)        │
                └────────────────────┘

┌────────────┐
│   MinIO    │  ← raw file storage (PDFs, DOCX, etc.)
└────────────┘
```

---

## Document Upload and Processing

```
User uploads file
       │
       ▼
┌─────────────┐
│   FastAPI   │  ← validates request, saves metadata
└──────┬──────┘
       │
       ├──────────────────────┐
       ▼                      ▼
┌────────────┐         ┌────────────┐
│ PostgreSQL │         │   MinIO    │
│            │         │            │
│ document   │         │ raw file   │
│ version    │         │ stored     │
│ PROCESSING │         └────────────┘
└──────┬─────┘
       │
       ▼
┌─────────────┐
│    Redis    │  ← processing job queued
└──────┬──────┘
       │
       ▼
┌──────────────────────────────────┐
│           Worker Process          │
│                                  │
│  1. Fetch file from MinIO        │
│  2. OCR (if scanned)             │
│  3. Extract text                 │
│  4. Split into chunks            │
│  5. Generate embeddings          │
│  6. Store chunks + embeddings    │
│  7. Update version → ACTIVE      │
└──────────────────────────────────┘
       │
       ▼
┌────────────┐
│ PostgreSQL │  ← chunks + embeddings stored, status updated
└────────────┘
```

---

## Query Flow

```
User submits question
       │
       ▼
┌─────────────┐
│   FastAPI   │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│   Authentication    │  ← verify user identity
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Permission Filter  │  ← remove docs user cannot access
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Version Filter     │  ← keep only CURRENT versions
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Hybrid Retrieval   │
│                     │
│  Vector search      │  ← semantic similarity via pgvector
│  Full-text search   │  ← keyword match via PostgreSQL
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│     Ranking         │  ← merge and score results
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Context Assembly   │  ← build prompt with retrieved chunks
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│      OpenAI         │  ← generate answer
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Answer + Citations │  ← source, version, status returned
└─────────────────────┘
```

---

## Data Storage

```
PostgreSQL
├── users
├── documents
├── document_versions      ← versioned, one CURRENT per document
├── document_chunks        ← text + pgvector embeddings
├── document_permissions   ← reserved for future per-doc grants (MVP uses role+sensitivity)
├── processing_jobs        ← async job state
└── audit_events           ← immutable event log

MinIO
└── raw files              ← original uploads, retrievable by version

Redis
└── processing queue       ← jobs waiting for workers
```

---

## Infrastructure (Local / MVP)

```
Docker Compose
├── react (frontend)
├── fastapi (backend)
├── postgresql (database + vector search)
├── minio (file storage)
└── redis (job queue)
```

All services run locally via Docker Compose. One command brings the full stack up.
