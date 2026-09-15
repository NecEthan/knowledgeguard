# Architecture

## Technology Choices

---

### Frontend — React

React is a lightweight, component-based library that allows us to include only the libraries we need.

A framework like Angular ships with a large amount of built-in functionality that this project would not use. React keeps the frontend lean and focused.

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

### Docker

Docker removes the need to install and configure PostgreSQL, Redis, and MinIO directly on a local machine. Each service runs in its own container, spun up from an image.

Any developer can clone the project and bring the full infrastructure up with a single command. This ensures everyone runs the same versions of every service and eliminates environment-specific setup issues.
