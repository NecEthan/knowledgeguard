# MVP

## Data Sources

The MVP supports:

1. File uploads
2. PDF
3. DOCX
4. TXT
5. Markdown
6. Google Docs

The initial product intentionally starts with simple sources before expanding into larger enterprise ecosystems.

## Document Management

Users can:

1. Upload documents
2. View documents
3. Update documents
4. Delete documents
5. View metadata
6. View processing status
7. View document history

## Versioning

Every document update creates a new immutable version.

Example:

```text
Annual Leave Policy

v3  CURRENT
v2  SUPERSEDED
v1  SUPERSEDED
```

Only one version can be current at any time.

Normal AI queries retrieve the current version.

Historical queries can explicitly retrieve previous versions.

## AI Search

Users can ask questions such as:

```text
How many days of annual leave do employees receive?
```

The system:

```text
User Query
    ↓
Authentication
    ↓
Permission Check
    ↓
Current Version Filtering
    ↓
Knowledge Retrieval
    ↓
Ranking
    ↓
LLM
    ↓
Answer + Citations
```

## Citations

AI responses show:

1. Source document
2. Version
3. Document status
4. Last updated information

Example:

```text
Annual Leave Policy
Version 3
Current
Updated 14 September 2026
```

## Permissions

Users must only retrieve information they are authorised to access.

Permission filtering happens before content is sent to the LLM.

This prevents unauthorised documents from becoming AI context.

## Deletion

Deleting a document must remove it from the AI knowledge system.

This includes handling:

1. Original document
2. Extracted text
3. Chunks
4. Embeddings
5. Search indexes
6. Caches

A document should not appear in AI results after deletion.

## Audit Log

Important actions are recorded.

Example:

```text
14 Sep 2026 18:02
USER QUERY
"What is the annual leave policy?"
Retrieved Annual Leave Policy v3
Permission ALLOWED

14 Sep 2026 17:41
USER UPLOAD
Annual Leave Policy v3
Previous v2
New v3 CURRENT

14 Sep 2026 17:42
SYSTEM INDEX UPDATE
Removed v2
Indexed v3
```

## Knowledge Health

The dashboard provides an overview of the knowledge system.

```text
128 Documents
91 Current Versions
7 Review Required
3 Processing Failures
2 Permission Issues
```

---

# Example User Journey

### 1. Upload

A user uploads:

```text
Annual Leave Policy v1
```

### 2. Process

The system extracts the content, creates chunks, generates embeddings, and indexes the document.

### 3. Ask

The user asks:

```text
How many days annual leave do employees receive?
```

The AI answers using v1.

### 4. Update

The company uploads an updated policy.

```text
Annual Leave Policy v2
```

The system changes:

```text
v1  SUPERSEDED
v2  CURRENT
```

### 5. Ask Again

The same question now retrieves v2.

### 6. Historical Query

The user asks:

```text
What did the annual leave policy say before the latest version?
```

The system intentionally retrieves v1.

### 7. Delete

The policy is deleted.

The document and associated AI retrieval data are removed.

### 8. Permission Test

An unauthorised user attempts to ask about the document.

The document is not included in their retrieval context.

### 9. Audit

The entire lifecycle can be inspected through the audit log.

---

# Document Lifecycle

```text
PROCESSING
    ↓
ACTIVE
    ↓
SUPERSEDED
    ↓
DELETED
```

Documents can also enter:

```text
REVIEW_REQUIRED
```

when they require review or have exceeded a configured review period.

---

# Document Processing Architecture

```text
Upload
   ↓
API
   ↓
Database + Object Storage
   ↓
Processing Queue
   ↓
Worker
   ↓
Text Extraction
   ↓
Chunking
   ↓
Embeddings
   ↓
Vector / Search Index
   ↓
READY
```

Processing is asynchronous so large documents do not block API requests.

Workers handle failures and retries.

Processing jobs are designed to be idempotent so duplicate events do not create duplicate indexed content.

---

# Google Docs Integration

The MVP also supports Google Docs.

```text
Google OAuth
    ↓
Select Document
    ↓
Import Content
    ↓
Create Version
    ↓
Process
    ↓
Index
```

When the document changes:

```text
Change Detected
    ↓
Create New Version
    ↓
Previous Version SUPERSEDED
    ↓
Process New Version
    ↓
Update Index
```

---

# AI Retrieval

The retrieval system is designed around version and permission correctness.

```text
User Query
     ↓
Authentication
     ↓
Permission Filtering
     ↓
Current Version Filtering
     ↓
Hybrid Retrieval
     ↓
Ranking
     ↓
Context Construction
     ↓
LLM
     ↓
Answer
     ↓
Citations
```

The system should never simply retrieve the most semantically similar document.

It must first determine whether that document is:

1. Current
2. Active
3. Authorised
4. Relevant

---

# Evaluation

The platform includes an evaluation dataset containing:

```text
Question
Expected Answer
Expected Source
Expected Version
User Permission
```

Metrics include:

1. Retrieval accuracy
2. Correct version accuracy
3. Answer accuracy
4. Citation accuracy
5. Permission accuracy
6. Stale retrieval rate

A key target is:

```text
0% stale retrieval
```

for normal current information queries.

---

# Architecture

```text
                    ┌──────────────────┐
                    │     Web App      │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │    API Layer     │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌────────────┐ ┌────────────┐ ┌────────────┐
       │ Documents  │ │   Query    │ │    Auth    │
       └─────┬──────┘ └─────┬──────┘ └────────────┘
             │              │
             ▼              ▼
       ┌────────────┐ ┌────────────┐
       │ PostgreSQL │ │ Retrieval  │
       └────────────┘ └─────┬──────┘
                            │
                    ┌───────┴────────┐
                    ▼                ▼
              ┌──────────┐    ┌──────────┐
              │  Vector  │    │  Search  │
              │    DB    │    │  Index   │
              └────┬─────┘    └────┬─────┘
                   └───────┬───────┘
                           ▼
                      ┌─────────┐
                      │   LLM   │
                      └─────────┘
```

Document processing runs asynchronously:

```text
API
 ↓
Queue
 ↓
Workers
 ↓
Extraction
 ↓
Chunking
 ↓
Embeddings
 ↓
Indexing
```

---

# Data Model

Core entities:

```text
users

documents

document_versions

document_permissions

document_chunks

processing_jobs

audit_events
```

Example document:

```text
documents
    id
    title
    owner_id
    source_type
    created_at
    deleted_at
```

Example version:

```text
document_versions
    id
    document_id
    version_number
    status
    content_hash
    created_at
    created_by
```

Example chunk:

```text
document_chunks
    id
    document_version_id
    content
    embedding
    metadata
```

---

# Core API

Example REST endpoints:

```text
POST   /documents
GET    /documents
GET    /documents/:id
PATCH  /documents/:id
DELETE /documents/:id

POST   /documents/:id/versions
GET    /documents/:id/versions
GET    /documents/:id/history

POST   /query

GET    /audit
```

---

# UI

## Dashboard

```text
Knowledge Overview

128 Documents
91 Current Versions
7 Review Required
3 Processing Failures
2 Permission Issues
```

## AI Search

```text
Ask your company knowledge

[ What is the annual leave policy? ]

Answer

Employees receive ...

Source
Annual Leave Policy

Version
v3 CURRENT

Updated
14 September 2026
```

## Documents

```text
Name                  Source       Version    Status

Annual Leave Policy   Upload       v3         CURRENT
Security Policy       Google Docs  v4         CURRENT
Employee Handbook     Upload       v2         CURRENT
```

## Version History

```text
Annual Leave Policy

v3  CURRENT
v2  SUPERSEDED
v1  SUPERSEDED
```

Users can inspect previous versions and compare changes.

## Audit Log

Shows document changes, queries, permission decisions, indexing events, and lifecycle transitions.

## Observability

Important metrics include:

```text
API latency
Document processing latency
Queue depth
Processing failures
Search latency
Retrieval latency
LLM latency
Token usage
Cost per query
Stale retrievals
```

## Auditability

Important knowledge lifecycle events must be traceable.

---

# MVP Roadmap

## Phase 1: Foundation

1. Project setup
2. Authentication
3. PostgreSQL
4. Object storage
5. Document API
6. Basic UI

## Phase 2: Document Processing

1. PDF processing
2. DOCX processing
3. Text extraction
4. Chunking
5. Embeddings
6. Vector search
7. Processing workers
8. Retry handling

## Phase 3: AI

1. Natural language queries
2. RAG
3. Citations
4. Current version filtering
5. Retrieval evaluation
6. Answer evaluation

## Phase 4: Knowledge Lifecycle

1. Document versioning
2. Superseded versions
3. Historical queries
4. Deletion
5. Index synchronisation
6. Audit logging

## Phase 5: Security

1. RBAC
2. Document permissions
3. Permission aware retrieval
4. Security testing
5. Access audit logs

## Phase 6: Google Docs

1. OAuth
2. Document import
3. Change detection
4. Version creation
5. Reindexing

---

# Success Criteria

The MVP should demonstrate:

```text
Current version retrieval works correctly

Superseded versions are excluded from normal queries

Historical versions can be intentionally retrieved

Deleted documents cannot be retrieved

Unauthorised users cannot retrieve restricted content

Every AI answer has traceable sources

Document processing failures are visible

Document lifecycle changes are auditable

Duplicate processing is handled safely
```

The system should ultimately optimise for:

```text
Correct information
+
Correct version
+
Correct permissions
+
Traceable source
=
Trustworthy enterprise AI
```

---

# Why This Is More Than a RAG Demo

KnowledgeGuard is not primarily a chatbot.

The interesting engineering problems are around the infrastructure behind the AI:

1. Document lifecycle management
2. Version consistency
3. Permission aware retrieval
4. Distributed processing
5. Index synchronisation
6. Deletion propagation
7. Auditability
8. Retrieval evaluation
9. Observability
10. Enterprise integrations

The LLM is only one component of the system.

The core product is the governed knowledge layer that makes enterprise AI more reliable.

---

# Project Goal

Build a production style enterprise knowledge platform that demonstrates how AI systems can be made more reliable through strong software engineering, data governance, security, observability, and lifecycle management.

**KnowledgeGuard: the trusted knowledge layer for enterprise AI.**
