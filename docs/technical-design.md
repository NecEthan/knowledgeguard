# Technical Design Document

**Project:** KnowledgeGuard
**Scope:** MVP

---

## 1. Overview

KnowledgeGuard is an enterprise knowledge platform that allows employees to ask natural language questions and receive accurate answers from company documents. The system guarantees that answers are sourced from the current, authorised version of each document and that every answer is traceable to its source.

---

## 2. Frontend Design

### Route Protection

A proxy is used to redirect a user to an appropriate page if they try to access a page that does not exist or that they are not authorised to access. The proxy is not the security boundary because a user can bypass the frontend and directly request data from the backend API. The backend therefore performs the actual authentication and authorisation checks.

### Authentication

A session cookie is used. The browser stores only the session identifier and automatically includes the cookie with requests to the backend over HTTPS.

The session is managed by the backend, allowing sessions to be invalidated when required. Using an `HttpOnly` cookie prevents client-side JavaScript from directly reading the session cookie, reducing the risk of the authentication credential being exposed through an XSS vulnerability.

The cookie is configured with the `Secure` attribute, meaning the browser will only send it over HTTPS. The browser automatically attaches the cookie to requests to the relevant backend when making authenticated requests.

To help prevent CSRF attacks, the `SameSite=Strict` cookie attribute is set, which prevents the browser from sending the cookie with cross-site requests, reducing the risk of an attacker making authenticated requests on the user's behalf.

### File Uploads

The frontend restricts the file types and file sizes that can be selected to provide immediate feedback to the user. These restrictions cannot be trusted as a security boundary, so the backend independently validates every uploaded file.

### Processing State

Document processing is asynchronous, so the frontend represents the document's current processing state — uploading, uploaded, processing, completed, or failed. The frontend retrieves the current state from the backend rather than assuming processing has completed.

### Error Handling

The frontend provides user-friendly error messages without exposing internal backend errors or implementation details.

### Loading and Duplicate Actions

The frontend provides appropriate loading states and prevents accidental duplicate submissions where possible. The backend remains responsible for preventing duplicate processing because frontend controls can be bypassed.

---

## 3. Backend Design

### Authentication

The backend validates the user's session on protected requests. The session is stored server-side so it can be invalidated when required.

### Authorisation

Authentication only establishes who the user is. The backend also performs authorisation checks to determine whether the user has permission to access the requested resource. These checks are performed on every protected resource rather than relying on the frontend.

### API Validation

All data received from the frontend is validated by the backend. The backend cannot rely on frontend validation because requests can be made directly to the API.

### File Uploads

The backend independently validates uploaded files, including file type and size, before accepting them for processing. Files are assigned a unique identifier and stored separately from the application database.

### Document Integrity

A SHA-256 hash is generated for each uploaded document. This provides a way to verify the document has not changed and can also be used to identify duplicate documents where appropriate.

### Asynchronous Processing

Document processing is separated from the API request using a background job queue. The API accepts the document and creates a processing job rather than keeping the HTTP request open while OCR and AI processing takes place.

### Job Reliability

Workers process jobs independently of the API. Failed jobs are retried with exponential backoff, while a maximum retry count prevents permanently failing documents from being retried indefinitely.

### Idempotency

Processing operations are designed to be idempotent so that retrying a job does not incorrectly create duplicate records or repeat completed work.

### Database Transactions

Database changes are performed within transactions where multiple related records need to remain consistent. Long-running operations such as AI API calls are not performed while holding a database transaction open.

### AI Processing

AI processing is treated as an unreliable external dependency. The backend validates AI responses against the expected schema rather than assuming the model will always return valid data.

### Secrets

API keys and other credentials are stored as environment or secret configuration rather than being exposed to the frontend or committed to source control.

### Rate Limiting

API endpoints that are expensive or can be abused — particularly document uploads and processing requests — are rate limited to prevent excessive resource consumption.

### Observability

The backend records structured logs and processing metrics such as job duration, retry count, processing status, and failures so that problems can be diagnosed without relying on the frontend.

### Resource Limits

Limits are placed on document size, processing attempts, and worker concurrency to prevent a single request or document from consuming an unreasonable amount of system resources.

---

## 4. Data Model

### `users`

```sql
id            UUID PRIMARY KEY
email         TEXT UNIQUE NOT NULL
password_hash TEXT NOT NULL
role          TEXT NOT NULL  -- admin | user
created_at    TIMESTAMPTZ NOT NULL
```

### `documents`

```sql
id          UUID PRIMARY KEY
title       TEXT NOT NULL
owner_id    UUID REFERENCES users(id)
source_type TEXT NOT NULL   -- upload | google_docs
sensitivity TEXT NOT NULL   -- STANDARD | SENSITIVE
created_at  TIMESTAMPTZ NOT NULL
deleted_at  TIMESTAMPTZ     -- soft delete
```

### `document_versions`

```sql
id             UUID PRIMARY KEY
document_id    UUID REFERENCES documents(id)
version_number INTEGER NOT NULL
status         TEXT NOT NULL  -- PROCESSING | ACTIVE | SUPERSEDED | DELETED | REVIEW_REQUIRED
content_hash   TEXT NOT NULL  -- SHA-256 of extracted text
storage_key    TEXT NOT NULL  -- MinIO object key
created_at     TIMESTAMPTZ NOT NULL
created_by     UUID REFERENCES users(id)

UNIQUE (document_id, version_number)
```

Only one version per document can have `status = ACTIVE` at any time. Enforced at the application layer and verified with a partial unique index.

```sql
CREATE UNIQUE INDEX one_active_version_per_document
ON document_versions (document_id)
WHERE status = 'ACTIVE';
```

### `document_chunks`

```sql
id                  UUID PRIMARY KEY
document_version_id UUID REFERENCES document_versions(id)
chunk_index         INTEGER NOT NULL
content             TEXT NOT NULL
embedding           vector(1536)  -- pgvector column
token_count         INTEGER NOT NULL
metadata            JSONB
```

### `document_permissions`

```sql
id          UUID PRIMARY KEY
document_id UUID REFERENCES documents(id)
user_id     UUID REFERENCES users(id)
granted_by  UUID REFERENCES users(id)
created_at  TIMESTAMPTZ NOT NULL

UNIQUE (document_id, user_id)
```

### `processing_jobs`

```sql
id                  UUID PRIMARY KEY
document_version_id UUID REFERENCES document_versions(id)
status              TEXT NOT NULL  -- QUEUED | PROCESSING | COMPLETE | FAILED
attempts            INTEGER NOT NULL DEFAULT 0
last_error          TEXT
created_at          TIMESTAMPTZ NOT NULL
updated_at          TIMESTAMPTZ NOT NULL
```

### `audit_events`

```sql
id         UUID PRIMARY KEY
event_type TEXT NOT NULL  -- UPLOAD | QUERY | DELETE | VERSION_SUPERSEDED | PERMISSION_DENIED | ...
user_id    UUID REFERENCES users(id)
document_id UUID
version_id  UUID
metadata   JSONB  -- query text, retrieved version, permission result, etc.
created_at TIMESTAMPTZ NOT NULL
```

Audit events are append-only. No updates or deletes.

---

## 5. API Design

### Authentication

```
POST   /auth/register
POST   /auth/login
POST   /auth/logout
GET    /auth/user
```

On login, the backend creates a server-side session and sends the session ID to the browser as an `HttpOnly`, `Secure`, `SameSite=Strict` cookie. The browser automatically includes the cookie with subsequent requests over HTTPS.

### Documents

```
POST   /documents                    -- upload new document
GET    /documents                    -- list documents (filtered by permission)
GET    /documents/:id                -- get document metadata
PATCH  /documents/:id                -- update title / metadata
DELETE /documents/:id                -- soft delete, trigger index removal
```

### Versions

```
POST   /documents/:id/versions       -- upload new version
GET    /documents/:id/versions       -- list all versions
GET    /documents/:id/versions/:vid  -- get specific version metadata
```

### Query

```
POST   /query
```

Request body:

```json
{
  "question": "How many days of annual leave do employees receive?",
  "mode": "current"  // current | historical
}
```

Response:

```json
{
  "answer": "Employees receive 25 days of annual leave per year.",
  "citations": [
    {
      "document_title": "Annual Leave Policy",
      "version_number": 3,
      "status": "ACTIVE",
      "updated_at": "2026-09-14T17:41:00Z"
    }
  ]
}
```

### Audit

```
GET    /audit                        -- paginated audit log (admin only)
GET    /audit/:document_id           -- audit log for a specific document
```

### Health

```
GET    /health                       -- service health check
```

---

## 6. Document Processing Pipeline

Processing runs asynchronously. The API never blocks on it.

### Steps

1. **Receive upload** — API validates file type and size, saves metadata to PostgreSQL with `status = PROCESSING`, stores raw file in MinIO, enqueues a processing job in Redis
2. **OCR** — if the file is a scanned PDF or image, extracts text from each page
3. **Text extraction** — PyMuPDF (PDF), python-docx (DOCX), or plain read (TXT/MD) extracts clean text
4. **Chunking** — text is split into overlapping chunks of ~500 tokens with ~50 token overlap to preserve context at boundaries
5. **Embedding** — each chunk is sent to the OpenAI Embeddings API (`text-embedding-3-small`) and the returned vector is stored in `document_chunks.embedding`
6. **Index update** — PostgreSQL full-text search vectors updated via `tsvector`
7. **Status transition** — version moved to `ACTIVE`, previous version moved to `SUPERSEDED`, audit event emitted

### Idempotency

Each processing job includes a `content_hash` (SHA-256 of extracted text). Before writing chunks, the worker checks whether chunks already exist for this version and hash. Duplicate runs produce no duplicate data.

### Failure Handling

Jobs are retried up to 3 times with exponential backoff. After 3 failures, `status = FAILED` and the error is recorded. Processing failures appear in the Knowledge Health dashboard.

---

## 7. Retrieval Pipeline

The retrieval pipeline runs on every query. Order of operations is fixed and cannot be bypassed.

### Step 1 — Authentication

Request must include a valid session cookie. The backend validates the session ID against the server-side session store. If missing, invalid, or expired, return `401`. Log the attempt.

### Step 2 — Permission Filtering

Load the set of document IDs the authenticated user is permitted to access based on their role. Non-admins are restricted to `SENSITIVE != 'SENSITIVE'` documents. All subsequent retrieval is scoped to this set. Sensitive documents never appear in results for non-admin users under any circumstances.

### Step 3 — Version Filtering

Within the permitted set, filter further to only `ACTIVE` versions. Superseded and deleted versions are excluded from normal queries.

For `mode = historical`, the filter relaxes to include `SUPERSEDED` versions where the query indicates historical intent.

### Step 4 — Hybrid Retrieval

Two retrieval methods run in parallel:

**Vector search** — the query is embedded using the same OpenAI model used at index time. pgvector finds the top-K most similar chunks by cosine similarity, restricted to the permitted + active version set.

**Full-text search** — PostgreSQL `tsvector` / `tsquery` keyword search over the same restricted set.

Results from both are merged.

### Step 5 — Ranking

Reciprocal Rank Fusion (RRF) merges the two result lists into a single ranked list. Top chunks are selected for context assembly.

### Step 6 — Context Assembly

Selected chunks are formatted into a prompt with the user's question. Source document title, version number, and status are included so the LLM can cite them accurately.

### Step 7 — LLM Generation

Assembled prompt sent to OpenAI. The model is instructed to answer only from the provided context and to include citations. If context does not contain the answer, the model must say so rather than hallucinate.

### Step 8 — Response

Answer and structured citations returned to the client.

---

## 8. Version Transition

When a new version is uploaded:

1. New `document_version` record created with `status = PROCESSING`
2. Processing pipeline runs
3. On success, inside a single database transaction:
   - Current `ACTIVE` version updated to `SUPERSEDED`
   - New version updated to `ACTIVE`
   - Old chunks remain in the database but are no longer reachable via normal queries (version filter excludes them)
   - Audit event emitted for both transitions
4. On failure, new version moves to `FAILED`. Previous `ACTIVE` version remains active.

Transition is atomic. There is never a moment where zero versions are active (assuming one existed before).

---

## 9. Deletion

Deleting a document triggers a multi-step cleanup. All steps must complete before the document is considered fully removed.

1. `documents.deleted_at` set to current timestamp (soft delete)
2. All versions for the document set to `DELETED`
3. All `document_chunks` for all versions deleted
4. pgvector embeddings removed
5. Full-text search index entries removed
6. Redis job queue checked — any in-flight processing jobs for this document are cancelled
7. Audit event emitted

After deletion, the document cannot appear in any query result. The permission filter excludes soft-deleted documents. The version filter excludes `DELETED` versions.

---

## 10. Authentication and Authorisation

### Authentication

Session cookie-based. On login, the backend creates a server-side session containing `user_id` and `role`, and sends the session ID to the browser as an `HttpOnly`, `Secure`, `SameSite=Strict` cookie. Sessions are stored server-side and can be invalidated at any time. Sessions expire after 24 hours of inactivity.

Passwords stored as bcrypt hashes. Minimum 8 characters enforced at registration.

### Authorisation

Role and document sensitivity together determine access. Ownership has no effect.

**Roles:**
- `admin` — full access to all documents (STANDARD and SENSITIVE)
- `user` — access to STANDARD documents only

**Document sensitivity:**
- `STANDARD` — accessible to all authenticated users
- `SENSITIVE` — accessible to admins only; non-admins cannot upload, list, read, or query sensitive documents

Permission filter applied at the DB query layer in every document route and in the RAG retrieval pipeline. `SENSITIVE` documents never enter the retrieval pipeline for non-admin users.

All new users register as `user`. Role is promoted via direct DB update (`UPDATE users SET role = 'admin'`). There is no self-service role elevation.

### Principle

Deny by default for sensitive content. STANDARD documents are accessible to all authenticated users. SENSITIVE documents are accessible only to admins.

---

## 11. Audit Log

All significant events are written to `audit_events` as append-only records.

Events captured:

| Event | Triggered by |
| --- | --- |
| `USER_REGISTERED` | Registration |
| `USER_LOGIN` | Login |
| `DOCUMENT_UPLOADED` | Upload |
| `VERSION_CREATED` | New version upload |
| `VERSION_SUPERSEDED` | Version transition |
| `DOCUMENT_DELETED` | Deletion |
| `QUERY_EXECUTED` | Any query |
| `PERMISSION_DENIED` | Failed permission check |
| `PROCESSING_FAILED` | Worker failure |
| `INDEX_UPDATED` | Successful indexing |

The audit log is not editable. No update or delete operations on `audit_events`.

---

## 12. Error Handling

| Scenario | Behaviour |
| --- | --- |
| Missing or invalid session cookie | `401 Unauthorized` |
| Permission denied | `403 Forbidden`, audit event written |
| Document not found | `404 Not Found` |
| Unsupported file type | `422 Unprocessable Entity` |
| Processing failure | Version marked `FAILED`, visible in dashboard |
| LLM API failure | `503 Service Unavailable`, query not answered |
| Duplicate processing job | Idempotency check prevents duplicate chunks |
| Version transition failure | Transaction rolled back, previous version stays `ACTIVE` |

---

## 13. Testing Strategy

### Unit Tests (Pytest)

- Version transition logic — correct status changes, atomic rollback on failure
- Permission filter — correct documents excluded for each user
- Version filter — only `ACTIVE` versions returned for normal queries
- Chunking — correct chunk size and overlap
- Deletion — all associated data removed

### Integration Tests (Pytest)

- Full upload → process → query flow
- Version supersede → query returns new version
- Delete → query returns no results
- Permission denied → restricted document not in results
- Historical query → superseded version retrieved correctly

### End-to-End Tests (Playwright)

- User signs up, uploads document, asks question, receives cited answer
- User uploads updated version, same question returns updated answer
- User deletes document, document no longer appears
- Unauthorised user cannot access restricted document

### Evaluation Dataset

Fixed test cases with known correct answers, sources, versions, and permissions. Run on every deployment. Tracks:

- Stale retrieval rate (target: 0%)
- Unauthorised retrieval rate (target: 0%)
- Correct version citation rate (target: 100%)
- Answer accuracy (target: 85%+)

---

## 14. Key Technical Decisions

### Why soft delete for documents?

Hard delete would immediately orphan chunk and embedding data. Soft delete allows the cleanup process to run completely before the document is considered gone. The audit log also retains a reference to the deleted document's ID.

### Why keep superseded chunks in the database?

Historical queries need access to superseded content. Deleting chunks on supersede would prevent legitimate historical retrieval. Chunks are excluded from normal queries by the version filter, not by deletion.

### Why run permission filtering before retrieval?

Filtering after retrieval would mean restricted content entered the retrieval pipeline as candidates. Even if excluded from the final answer, this would be a data handling concern. Filtering before retrieval ensures restricted documents are never loaded as context under any circumstances.

### Why store raw files in MinIO rather than PostgreSQL?

PostgreSQL is not optimised for large binary storage. Storing raw files in a dedicated object store keeps the database lean and keeps file reads off the database connection pool.

### Why pgvector over a dedicated vector database for the MVP?

A dedicated vector database (Qdrant, Pinecone) adds operational complexity — a second system to deploy, monitor, and keep in sync with the relational data. For MVP document volumes, pgvector is sufficient. The abstraction boundary means switching to a dedicated vector DB later is an infrastructure change, not an application logic change.
