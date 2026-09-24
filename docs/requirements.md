# Requirements

**Project:** KnowledgeGuard
**Source of truth:** `mvp.md`, `technical-design.md`, `final-product.md`

---

## MVP Requirements

### Authentication

1. Users can register with an email address and password (minimum 8 characters).
2. Passwords are stored as bcrypt hashes.
3. Users can log in and receive a server-side session.
4. The session ID is sent to the browser as an `HttpOnly`, `Secure`, `SameSite=Strict` cookie.
5. Sessions expire after 24 hours of inactivity.
6. Sessions can be invalidated server-side at any time.
7. Users can log out, invalidating their session immediately.
8. Users can retrieve their own profile (`GET /auth/user`).

---

### Authorisation

9. Two roles exist: `admin` and `user`.
10. Admins have full access to all documents (STANDARD and SENSITIVE) and the audit log.
11. Users can access STANDARD documents only. SENSITIVE documents are inaccessible to users regardless of who uploaded them.
12. Documents have a `sensitivity` field: `STANDARD` or `SENSITIVE`. Sensitivity must be set at upload time.
13. Only admins can upload SENSITIVE documents. A non-admin attempting to upload a SENSITIVE document receives `403 Forbidden`.
14. Authorisation checks are performed on every protected request at the backend. Ownership has no effect on access.

---

### Document Management

14. Users can upload documents in the following formats: PDF, DOCX, TXT, Markdown.
15. Users can connect and import Google Docs.
16. Users can view a list of their accessible documents.
17. Users can view document metadata (title, source type, created date, current version).
18. Users can update a document's title and metadata.
19. Users can upload a new version of an existing document.
20. Users can delete a document.
21. Users can view the full version history of a document.

---

### Document Versioning

22. Every document update creates a new immutable version.
23. Only one version per document can have status `ACTIVE` at any time. This is enforced at the database level with a partial unique index.
24. Version statuses are: `PROCESSING`, `ACTIVE`, `SUPERSEDED`, `DELETED`, `REVIEW_REQUIRED`.
25. When a new version becomes active, the previous active version transitions to `SUPERSEDED`.
26. The version transition (supersede old, activate new) is performed atomically in a single database transaction.
27. If a new version fails processing, the previous active version remains active.
28. A SHA-256 hash of the extracted text is stored per version for integrity verification and duplicate detection.

---

### Document Processing

29. Document processing runs asynchronously. The API does not block on processing.
30. On upload, the API validates the file, stores metadata in the database with status `PROCESSING`, stores the raw file in MinIO, and enqueues a processing job in Redis.
31. Workers process jobs independently of the API.
32. Processing steps: OCR (if scanned), text extraction, chunking (~500 tokens, ~50 token overlap), embedding generation, vector index update, full-text search index update.
33. Embeddings are generated using OpenAI `text-embedding-3-small` and stored in the `document_chunks.embedding` pgvector column.
34. Failed jobs are retried up to 3 times with exponential backoff.
35. After 3 failures, the version is marked `FAILED` and the error is recorded.
36. Processing operations are idempotent. Retrying a job does not create duplicate chunks or embeddings.
37. The frontend displays the current processing status of each document.
38. Processing failures are visible in the Knowledge Health dashboard.

---

### AI Query

39. Users can submit natural language questions via `POST /query`.
40. Every query goes through this pipeline in order, with no step skippable:
    1. Session authentication
    2. Permission filtering (restrict to documents the user can access)
    3. Version filtering (restrict to `ACTIVE` versions by default)
    4. Hybrid retrieval (vector search via pgvector and full-text search via PostgreSQL `tsvector`)
    5. Ranking (Reciprocal Rank Fusion merges vector and full-text results)
    6. Context assembly
    7. LLM generation (OpenAI)
    8. Answer and citations returned
41. Permission filtering happens before any document content enters the retrieval pipeline. Restricted documents are never loaded as context under any circumstances.
42. A `historical` query mode relaxes the version filter to include `SUPERSEDED` versions.
43. Every answer includes citations: document title, version number, version status, and last updated date.
44. If the context does not contain the answer, the LLM must say so rather than generate an answer.
45. If the LLM API is unavailable, the query returns `503 Service Unavailable`.
46. AI responses do not expose raw backend errors or internal implementation details.

---

### Deletion

48. All versions for the document are set to `DELETED`.
49. All `document_chunks` for all versions are deleted.
50. pgvector embeddings and full-text search index entries are removed.
51. Any in-flight processing jobs for the document are cancelled.
52. An audit event is emitted for the deletion.
53. A deleted document cannot appear in any query result.

---

### Permissions

54. Access is governed by user role and document sensitivity. There are no per-document permission grants in the MVP.
55. Permission checks (role vs sensitivity) are performed before content is retrieved on every query.
56. SENSITIVE documents are excluded from all retrieval pipelines for non-admin users.

---

### Audit Log

57. The following events are recorded as append-only audit records: `USER_REGISTERED`, `USER_LOGIN`, `DOCUMENT_UPLOADED`, `VERSION_CREATED`, `VERSION_SUPERSEDED`, `DOCUMENT_DELETED`, `QUERY_EXECUTED`, `PERMISSION_DENIED`, `PROCESSING_FAILED`, `INDEX_UPDATED`.
58. Audit records are never updated or deleted.
59. Admins can view a paginated audit log via `GET /audit`.
60. Admins can view the audit log for a specific document via `GET /audit/:document_id`.

---

### Knowledge Health Dashboard

61. The dashboard displays: total document count, documents with a current active version, documents flagged as review required, documents with processing failures, and documents with permission issues.

---

### Security

62. The backend validates all uploaded files independently of frontend validation, including file type and file size.
63. API endpoints that are expensive or can be abused, particularly document uploads and query endpoints, are rate limited.
64. API keys and credentials are stored as environment variables and are never committed to source control or exposed to the frontend.
65. Database changes involving multiple related records are performed within transactions.
66. Long-running operations (AI API calls) are not performed while a database transaction is open.
67. AI responses are validated against the expected schema before being used.

---

### Observability

68. The backend records structured logs.
69. Processing metrics are recorded: job duration, retry count, processing status, and failures.
70. The following metrics are tracked: API latency, document processing latency, queue depth, processing failures, search latency, retrieval latency, LLM latency, token usage, cost per query, stale retrieval rate.

---

### Infrastructure

71. All services run locally via Docker Compose: Next.js frontend, FastAPI backend, PostgreSQL, MinIO, Redis.
72. A single command brings the full local stack up.

---

### Testing

73. Unit tests cover: version transition logic, permission filtering, version filtering, chunking, deletion cleanup.
74. Integration tests cover: full upload-process-query flow, version supersede, deletion, permission denial, historical query.
75. End-to-end tests (Playwright) cover: sign up, upload, query, version update, deletion, unauthorised access.
76. An evaluation dataset with known correct answers, sources, versions, and permissions runs on every deployment.
77. Target metrics: 0% stale retrieval rate, 0% unauthorised retrieval rate, 100% correct version citation rate, 85%+ answer accuracy.

---

### API

78. The API exposes the following endpoints:

```
POST   /auth/register
POST   /auth/login
POST   /auth/logout
GET    /auth/user

POST   /documents
GET    /documents
GET    /documents/:id
PATCH  /documents/:id
DELETE /documents/:id

POST   /documents/:id/versions
GET    /documents/:id/versions
GET    /documents/:id/versions/:vid

POST   /query

GET    /audit
GET    /audit/:document_id

GET    /health
```

---

## Production Requirements

### Enterprise Connectors

79. The platform connects to and synchronises documents from: Microsoft SharePoint, OneDrive, Microsoft Teams, Google Drive, Google Docs, Confluence, Notion, and internal APIs.
80. KnowledgeGuard acts as the governance and AI retrieval layer on top of existing enterprise knowledge systems, not a replacement for them.

---

### Event-Driven Synchronisation

81. When a document is created in a connected source, KnowledgeGuard automatically creates a new version and processes it.
82. When a document is updated in a connected source, KnowledgeGuard creates a new version, supersedes the previous version, and reprocesses.
83. When a document is deleted in a connected source, KnowledgeGuard propagates the deletion.
84. Permission changes in connected sources are synchronised.

---

### Advanced Search and Retrieval

85. Hybrid search (vector + full-text) is used across all connected sources.
86. A reranking step improves result quality after initial retrieval.

---

### Advanced Permissions

87. Enterprise-level permissions support group-based and role-based access controls beyond the basic user/admin model.

---

### Stale and Conflict Detection

88. The platform detects documents that have not been reviewed within a configured period and flags them as `REVIEW_REQUIRED`.
89. The platform detects multiple documents containing conflicting information and surfaces them in the Knowledge Health dashboard.
90. The platform detects and alerts on: incomplete processing, unsynchronised permission changes, deleted documents still present in an index, and connectors that have stopped synchronising.

---

### Advanced Audit and Observability

91. The audit log captures advanced lifecycle events across all connected sources.
92. The Knowledge Health dashboard provides detailed diagnostics across the full enterprise knowledge estate.

---

### Evaluation Framework

93. The evaluation framework is extended to cover all connected sources, with automated accuracy tracking on every deployment.
94. Evaluation tracks retrieval accuracy, correct version accuracy, answer accuracy, citation accuracy, permission accuracy, and stale retrieval rate across the full knowledge estate.

---

### API Access

95. The platform exposes a public API so internal AI applications, chat systems, and agents can query the knowledge base programmatically.
