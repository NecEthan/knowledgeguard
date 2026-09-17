# Production Requirements

**Project:** KnowledgeGuard
**Source of truth:** `final-product.md`, `prod-architecture.md`, `technical-design.md`

All MVP requirements apply. This document defines the additional requirements for the production platform.

---

## Infrastructure and Deployment

1. The frontend is served via a CDN for static asset delivery.
2. The backend runs as multiple FastAPI instances behind a load balancer.
3. PostgreSQL runs as a primary and replica pair. Read queries can be served from the replica.
4. Vector storage is handled by a dedicated Qdrant cluster, separate from PostgreSQL. The pgvector approach used in the MVP is replaced with Qdrant to give vector and relational workloads independent resource headroom.
5. Redis runs as a cluster rather than a single instance.
6. MinIO or a cloud-equivalent object store is used for file storage.
7. Workers auto-scale based on queue depth. Multiple workers process jobs in parallel.
8. All infrastructure is cloud-hosted using managed services.

---

## Enterprise Connectors

9. The platform connects to and synchronises documents from: Microsoft SharePoint, Microsoft OneDrive, Microsoft Teams, Google Drive, Google Docs, Confluence, Notion, and internal APIs via webhooks or polling.
10. KnowledgeGuard acts as the governance and AI retrieval layer on top of these systems, not a replacement for them. Source systems remain the authoritative store.
11. Each connector resolves permissions from the source system and propagates them to KnowledgeGuard.

---

## Event-Driven Synchronisation

12. When a document is created in a connected source, the connector service detects the event, fetches the content, resolves permissions, and creates a new version via the KnowledgeGuard API.
13. When a document is updated in a connected source, the connector creates a new version, the previous version is superseded, and the new version is processed and indexed.
14. When a document is deleted in a connected source, the deletion is propagated through the full KnowledgeGuard deletion pipeline.
15. Permission changes in connected sources are synchronised. A user losing access in the source system loses access in KnowledgeGuard.
16. Connector sync health is monitored. A connector that stops synchronising is surfaced in the Knowledge Health dashboard.

---

## Authentication and Authorisation

17. Enterprise SSO is supported, allowing users to authenticate via their organisation's identity provider.
18. Group-based and role-based access controls are supported beyond the basic `admin`/`user` model.
19. Permission grants and revocations from connected source systems propagate automatically.

---

## Search and Retrieval

20. Vector search runs against Qdrant rather than pgvector. The retrieval pipeline abstraction means this is an infrastructure change with no change to application retrieval logic.
21. A reranking step using a cross-encoder model runs after initial hybrid retrieval and before context assembly, improving result quality at scale.
22. Hybrid retrieval (vector + full-text) covers all connected sources.

---

## Stale and Conflict Detection

23. The platform detects documents that have not been reviewed within a configured period and marks them `REVIEW_REQUIRED`.
24. The platform detects multiple documents containing conflicting information on the same topic and surfaces them in the Knowledge Health dashboard.
25. The platform detects and alerts on incomplete processing jobs.
26. The platform detects and alerts on permission sync failures.
27. The platform detects and alerts on documents still present in the search index after deletion.
28. The platform detects and alerts on connectors that have stopped synchronising.

---

## Knowledge Health Dashboard

29. The dashboard provides visibility across the full enterprise knowledge estate, including all connected sources.
30. The dashboard surfaces: documents requiring review, conflicting policy documents, incomplete processing jobs, permission sync failures, connector sync failures, and documents present in the index after deletion.
31. Processing failure rate and connector health are tracked per source system.

---

## Observability

32. API latency is tracked at p50, p95, and p99 percentiles.
33. Query latency, retrieval latency, and LLM latency are tracked separately.
34. LLM token usage and cost per query are tracked.
35. Processing queue depth and worker throughput are tracked.
36. Processing success and failure rates are tracked per source type and connector.
37. Stale retrieval rate is tracked from evaluation runs and reported in the observability stack.
38. Connector sync health is tracked per connector.

---

## Audit Log

39. The audit log captures lifecycle events across all connected sources, not only file uploads.
40. Connector sync events (document created, updated, deleted, permission changed) are recorded as audit events.
41. Audit log export is supported for compliance and external reporting purposes.

---

## Evaluation Framework

42. The evaluation framework covers all connected sources.
43. Automated accuracy tracking runs on every deployment across all sources.
44. The evaluation dataset is extended to cover multi-source scenarios, cross-version correctness, and permission correctness across connector-sourced documents.
45. Evaluation tracks: retrieval accuracy, correct version accuracy, answer accuracy, citation accuracy, permission accuracy, and stale retrieval rate.
46. Evaluation results are stored and compared across deployments to detect regressions.

---

## Public API

47. The platform exposes a public API so internal AI applications, chat systems, and agents can query the knowledge base programmatically.
48. The public API is authenticated and respects the same permission model as the web application.
49. API access is rate limited per consumer.
