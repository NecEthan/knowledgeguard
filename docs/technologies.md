# Architecture

## Technology Choices

---

### Frontend — Next.js

Next.js was chosen over using React alone because it provides the application structure and production features needed for a full web application while still using React for the UI.

It provides built in routing, server side capabilities, middleware, environment configuration and production optimisations, reducing the amount of additional tooling required to build the frontend.

---

### Backend — FastAPI

FastAPI needs to interact with LLMs, document processing libraries, OCR tools, and embedding models. Most of these have strong Python support, which makes integration straightforward and gives access to a wide range of relevant libraries.

Pydantic provides request and response validation out of the box. FastAPI's built-in OpenAPI support makes it easy to define and document the REST API without additional tooling.

---

### Database — PostgreSQL

PostgreSQL is a relational database that allows us to define clear relationships between data. Documents, versions, chunks, and permissions all reference each other using foreign keys, and this structure needs to be enforced at the database level.

PostgreSQL also supports vector storage and search through the `pgvector` extension, which means we can store embeddings alongside relational data without running a separate database. MySQL does not have a comparable extension in its ecosystem.

**Future consideration:** At scale, if vector and relational workloads start competing for the same resources, it may be worth extracting embeddings into a dedicated vector database such as Qdrant. A dedicated vector database is designed to optimise and scale large vector search workloads, and separating the two would give each more resource headroom under heavy load.

---

### File Storage — MinIO

MinIO is designed to store binary files such as PDFs, images, and Word documents. Keeping file storage separate from PostgreSQL means the database is not handling large binary reads and writes. MinIO retrieves large files more efficiently than a relational database would.

---

### Background Processing — Redis

Redis was chosen to support the background processing queue. We need to process documents in the background because this takes much longer, we have to read the file, run OCR, extract text, split into chunks, create embeddings, send to LLM and store the results. This allows us to process multiple documents at the same time with multiple workers running at the same time which allows for fast uploads. When a document is uploaded, the API can add a processing job to Redis instead of processing the document during the request. Workers can then pick up these jobs and process them asynchronously. This keeps the API responsive and allows us to add more workers if the processing workload increases.

---

### Database Access — SQLAlchemy

SQLAlchemy is used to interact with PostgreSQL from Python. It provides an ORM layer that maps database tables to Python classes, keeping database logic clean and testable without writing raw SQL throughout the codebase.

---

### Database Migrations — Alembic

Alembic manages database schema changes over time. Every change to the schema is tracked as a versioned migration file. This means the database can be reliably evolve as the application grows, and any environment can be brought to the correct schema state with a single command.

### OCR — Text Extraction from Scanned Documents

Some documents arrive as scanned images rather than machine-readable text. An OCR library extracts the text from these documents before they enter the processing pipeline. Without this step, scanned PDFs would have no retrievable content.

---

### Authentication and Authorisation

Authentication verifies who the user is. Authorisation controls what they are allowed to access. Both are critical in KnowledgeGuard because documents may be restricted to specific users or roles. Permission filtering happens before any content is sent to the LLM, ensuring restricted documents never enter the retrieval context for unauthorised users.

---

### Frontend Unit Testing — Vitest and React Testing Library

Vitest is used as the test runner for frontend unit tests. It integrates with Vite natively, making it fast and simple to configure. React Testing Library is used alongside it to test components by interacting with them the way a user would — querying by visible text and roles rather than implementation details.

Unit tests cover individual components, UI state logic, and data formatting. These run in milliseconds and catch regressions without requiring a running backend.

---

### Backend Unit Testing — Pytest

Pytest was chosen because it provides a simple and flexible testing framework that fits well with our Python and FastAPI backend. Its fixture system makes it straightforward to create reusable test data and dependencies for testing the retrieval pipeline, version filtering, permission checks, and document processing logic. This allows us to test the backend reliably without adding unnecessary complexity.

---

### End-to-End Testing — Playwright

Playwright was chosen because it provides reliable browser automation and strong support for modern web applications. Its ability to run tests across different browsers and handle multiple isolated browser sessions is useful for testing authentication and document permissions. This allows us to reliably test critical workflows such as uploading documents, querying them, verifying document versions, and ensuring users cannot access documents they do not have permission to view.

---

### Docker

Docker removes the need to install and configure PostgreSQL, Redis, and MinIO directly on a local machine. Each service runs in its own container, spun up from an image.

Any developer can clone the project and bring the full infrastructure up with a single command. This ensures everyone runs the same versions of every service and eliminates environment-specific setup issues.

---

### CI/CD — GitHub Actions

GitHub Actions is the CI/CD platform for KnowledgeGuard. It runs automatically on every pull request and every push, providing fast feedback before changes are merged or deployed.

#### CI Pipeline

Each CI run executes the following checks in order:

1. **Frontend lint** — ESLint validates code quality and catches errors before tests run
2. **Frontend tests** — Jest runs unit tests covering UI components and logic
3. **Backend tests** — Pytest runs unit and integration tests covering the API, processing logic, permission filtering, and retrieval pipeline
4. **Frontend build** — Next.js production build verifies the application compiles without errors
5. **Playwright E2E tests** — Browser tests verify critical user flows against the full running stack

A failed check stops the pipeline. Stages that follow a failure do not run. Failed Playwright runs produce screenshots, traces, and HTML reports as CI artifacts, making failures diagnosable without reproducing them locally.

#### CD Pipeline

A fully passing CI run on `main` automatically deploys the merged change to the **development environment**. Production deployment occurs after validation in Dev.

#### Pipeline Flow

```text
Developer
    ↓
Pull Request
    ↓
GitHub Actions
    ├── Lint
    ├── Jest
    ├── Pytest
    ├── Build
    └── Playwright
    ↓
Merge to main
    ↓
Automatic deployment → Dev
    ↓
Production
```

### Architecture Decision

GitHub Actions was chosen because it integrates directly with GitHub. Separate development and production environments are used, with changes automatically deployed to Dev after passing CI.
