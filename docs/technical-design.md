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

### Orphaned Upload Cleanup

File upload and database commit are two separate operations. If the process crashes after uploading to MinIO but before the database transaction commits, the object in MinIO has no corresponding `DocumentVersion` record. These orphaned objects would accumulate indefinitely without a cleanup mechanism.

To handle this, every uploaded object is immediately tagged `kg-orphan=true` in MinIO after the upload completes. A MinIO lifecycle rule (configured at application startup) auto-expires any object carrying this tag after 24 hours.

Once the database transaction commits successfully, the tag is removed. The window between upload and tag removal is typically milliseconds. If removal fails, the processing job will eventually fail when the worker tries to download a deleted object; the reaper then marks the job `FAILED` and the user can re-upload.

Both the tagging and tag-removal calls are best-effort — failures are logged but do not abort the request. This is intentional: the lifecycle rule is a safety net, not a hard dependency.

### Process Uploads

First we set job status to `processing` commit those changes to db to keep job status up to date. The second transation will persist those results (add documentChunks, update vector search with chunks for keyword search) and activate version which sets active version to superseded, sets document we are processing to active and then sets job status to complete.

We then commit these changes to db or if error occured all changes are automatically rolledback and our poll system will pick up the job because status is set to `QUEUED` if processing job failed.

If we did not immediately commit status to processing at the start then the poller may pick up the QUEUED job again while it is being processed because it looks for QUEUED jobs to be processed every now and then.

### Reaper  

I implented a reaper in case local server or cloud server loses power or stops working, in this event our python except block would not execute however the db changes would be automatically rolledback if not commited yet.

If our server dies just after setting job status to `processing` then our job would not be cleaned up in the except block setting status back to `QUEUED` therefore the job would not be picked up again by our poll system and would be stuck forever as status `processing`.

### Poller

I chose to use a poller system to ensure that processing jobs stored in PostgreSQL are eventually picked up by ARQ.

This provides protection against failures occurring between creating the processing job in PostgreSQL and successfully enqueueing the job in Redis/ARQ.

For example, if the application creates a job with a QUEUED status but crashes before the job is successfully enqueued, the job would remain in PostgreSQL without ever being processed.

The poller periodically checks PostgreSQL for QUEUED jobs and enqueues any jobs that have not yet been picked up by ARQ. This means that if an error or server crash occurs before enqueueing, the job can safely be discovered and processed later.

For errors that occur during processing, ARQ's retry mechanism is responsible for retrying the job. The poller provides an additional recovery mechanism for jobs that are stuck in the database before they reach the worker queue.

I would use an transation outbox pattern if we was needing to execute multiple different events in a queue in the background because instead of having multiple different tables tracking events we would have one which allows for one relaible, generic source of truth for events that need to be processed in the background.

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

**Logs**

The application writes structured logs to stdout/stderr. In local development, these logs can be viewed through Docker Desktop. In production, the cloud environment collects these logs through its logging system, allowing them to be searched and monitored.

**Audits**

The system records important business and security events, such as document access, document deletion, version creation, metadata changes, access denied events, and role changes. 
Audit events are stored in the database and exposed through a restricted admin interface so authorized administrators can review activity and investigate potential unauthorized access to sensitive information.
If the audit table grows significantly and begins to impact database performance or storage costs, older audit records can be archived to cheaper external storage at a later stage while keeping recent audit data in PostgreSQL.


### Resource Limits

Limits are placed on document size, processing attempts, and worker concurrency to prevent a single request or document from consuming an unreasonable amount of system resources.

---

## 4. Retrieval Pipeline

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

Deleting a document is a hard delete. All associated rows are removed from the database in FK-dependency order within a single transaction.

1. Audit event emitted (`DOCUMENT_DELETED`)
2. All `document_chunks` for all versions deleted
3. All `processing_jobs` for all versions deleted
4. All `document_versions` for the document deleted
5. The `document` row deleted

After deletion the document cannot appear in any query result. Access attempts return `404`.

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

| Event                | Triggered by            |
| -------------------- | ----------------------- |
| `USER_REGISTERED`    | Registration            |
| `USER_LOGIN`         | Login                   |
| `DOCUMENT_UPLOADED`  | Upload                  |
| `VERSION_CREATED`    | New version upload      |
| `VERSION_SUPERSEDED` | Version transition      |
| `VERSION_ACTIVATED`  | Manual version activate |
| `DOCUMENT_DELETED`   | Deletion                |
| `QUERY_EXECUTED`     | Any query               |
| `PERMISSION_DENIED`  | Failed permission check |
| `PROCESSING_FAILED`  | Worker failure          |
| `INDEX_UPDATED`      | Successful indexing     |

The audit log is not editable. No update or delete operations on `audit_events`.

---

## 12. Error Handling

| Scenario                          | Behaviour                                                |
| --------------------------------- | -------------------------------------------------------- |
| Missing or invalid session cookie | `401 Unauthorized`                                       |
| Permission denied                 | `403 Forbidden`, audit event written                     |
| Document not found                | `404 Not Found`                                          |
| Unsupported file type             | `422 Unprocessable Entity`                               |
| Processing failure                | Version marked `FAILED`, visible in dashboard            |
| LLM API failure                   | `503 Service Unavailable`, query not answered            |
| Duplicate processing job          | Idempotency check prevents duplicate chunks              |
| Version transition failure        | Transaction rolled back, previous version stays `ACTIVE` |

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

### Why keep superseded chunks in the database?

Historical queries need access to superseded content. Deleting chunks on supersede would prevent legitimate historical retrieval. Chunks are excluded from normal queries by the version filter, not by deletion.

### Why store raw files in MinIO rather than PostgreSQL?

PostgreSQL is not optimised for large binary storage. Storing raw files in a dedicated object store keeps the database lean and keeps file reads off the database connection pool.

### Why pgvector over a dedicated vector database for the MVP?

A dedicated vector database (Qdrant, Pinecone) adds operational complexity — a second system to deploy, monitor, and keep in sync with the relational data. For MVP document volumes, pgvector is sufficient. The abstraction boundary means switching to a dedicated vector DB later is an infrastructure change, not an application logic change.
