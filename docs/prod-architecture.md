# Production Architecture

---

## System Overview

```
                        Users
                          │
                          ▼
               ┌─────────────────────┐
               │         CDN         │  ← static frontend assets
               └──────────┬──────────┘
                          │
                          ▼
               ┌─────────────────────┐
               │    Load Balancer    │
               └──────────┬──────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
   │  FastAPI    │ │  FastAPI    │ │  FastAPI    │
   │ instance 1  │ │ instance 2  │ │ instance N  │
   └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
          └───────────────┼───────────────┘
                          │
          ┌───────────────┼──────────────────────────┐
          ▼               ▼               ▼          ▼
  ┌──────────────┐ ┌─────────────┐ ┌──────────┐ ┌──────────────────┐
  │  PostgreSQL  │ │    Qdrant   │ │  Redis   │ │      MinIO       │
  │   Primary    │ │  (vectors)  │ │  cluster │ │  (file storage)  │
  └──────┬───────┘ └─────────────┘ └────┬─────┘ └──────────────────┘
         │                               │
         ▼                               ▼
  ┌──────────────┐                ┌─────────────┐
  │  PostgreSQL  │                │   Workers   │  ← auto-scaling
  │   Replica    │                └─────────────┘
  └──────────────┘
```

---

## Document Processing at Scale

```
File uploaded / connector event received
               │
               ▼
        ┌─────────────┐
        │   FastAPI   │
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐
        │    Redis    │  ← job queued with priority
        └──────┬──────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐
│ Worker │ │ Worker │ │ Worker │  ← multiple workers process in parallel
└───┬────┘ └───┬────┘ └───┬────┘
    └──────────┼──────────┘
               │
               ▼
┌──────────────────────────────────┐
│         Processing Pipeline       │
│                                  │
│  1. Fetch raw file from MinIO    │
│  2. OCR (if scanned image)       │
│  3. Extract and clean text       │
│  4. Split into chunks            │
│  5. Generate embeddings          │
│  6. Write chunks → PostgreSQL    │
│  7. Write vectors → Qdrant       │
│  8. Update full-text index       │
│  9. Mark version ACTIVE          │
│  10. Emit audit event            │
└──────────────────────────────────┘
```

---

## Query Flow

```
User submits question
       │
       ▼
┌─────────────┐
│ Load Balancer│
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   FastAPI   │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│   Authentication    │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Permission Filter  │  ← resolved from PostgreSQL
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Version Filter     │  ← CURRENT versions only
└──────┬──────────────┘
       │
       ▼
┌──────────────────────────────────┐
│         Hybrid Retrieval          │
│                                  │
│  Vector search    → Qdrant       │
│  Full-text search → PostgreSQL   │
└──────────────────┬───────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │    Reranking    │  ← cross-encoder model scores results
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │ Context Assembly│
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │     OpenAI      │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │Answer + Citations│
         └─────────────────┘
```

---

## Enterprise Connectors

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  SharePoint  │  │ Google Drive │  │  Confluence  │  │    Notion    │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       └──────────────────┼──────────────────┼─────────────────┘
                          │  webhook / poll
                          ▼
               ┌─────────────────────┐
               │  Connector Service  │
               │                     │
               │  detect change      │
               │  fetch content      │
               │  resolve permissions│
               └──────────┬──────────┘
                          │
                          ▼
               ┌─────────────────────┐
               │  KnowledgeGuard API │
               │                     │
               │  create version     │
               │  supersede previous │
               │  queue processing   │
               └─────────────────────┘
```

---

## Knowledge Health and Observability

```
┌──────────────────────────────────────────────┐
│              Observability Stack              │
│                                              │
│  API latency (p50 / p95 / p99)              │
│  Query latency                               │
│  Retrieval latency                           │
│  LLM latency + token usage                  │
│  Processing queue depth                      │
│  Processing success / failure rates         │
│  Stale retrieval rate (from eval runs)      │
│  Connector sync health                      │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│            Knowledge Health Dashboard         │
│                                              │
│  Documents requiring review                 │
│  Conflicting policy documents detected      │
│  Incomplete processing jobs                 │
│  Permission sync failures                   │
│  Connector sync failures                    │
│  Documents present in index after deletion  │
└──────────────────────────────────────────────┘
```

---

## MVP vs Production Comparison

```
                  MVP                     Production
                   │                          │
Frontend      Single instance           CDN + static hosting
Backend       Single FastAPI            Load balanced, multiple instances
Database      PostgreSQL + pgvector     PostgreSQL primary + replica + Qdrant
File Storage  MinIO (local)             MinIO / cloud object storage
Queue         Redis (single)            Redis cluster
Workers       Single worker process     Multiple workers, auto-scaling
Connectors    File upload + Google Docs SharePoint, Drive, Confluence, Notion
Auth          Basic                     Enterprise SSO / RBAC
Search        Vector + full-text        Hybrid + reranking
Stale detect  Basic version filter      Proactive conflict and staleness detection
Infrastructure Docker Compose (local)   Cloud-hosted, managed services
```
