export type UserRole = "admin" | "user";

export interface User {
  id: string;
  email: string;
  role: UserRole;
  created_at: string;
}

export type DocumentSourceType = "upload" | "google_docs";

export interface Document {
  id: string;
  title: string;
  owner_id: string;
  source_type: DocumentSourceType;
  created_at: string;
  deleted_at: string | null;
}

export type DocumentVersionStatus =
  "PROCESSING" | "ACTIVE" | "SUPERSEDED" | "DELETED" | "REVIEW_REQUIRED";

export interface DocumentVersion {
  id: string;
  document_id: string;
  version_number: number;
  status: DocumentVersionStatus;
  content_hash: string;
  storage_key: string;
  created_at: string;
  created_by: string;
}

export type ProcessingJobStatus =
  "QUEUED" | "PROCESSING" | "COMPLETE" | "FAILED";

export interface QueryRequest {
  question: string;
  mode: "current" | "historical";
}

export interface QueryCitation {
  document_title: string;
  version_number: number;
  status: DocumentVersionStatus;
  updated_at: string;
}

export interface QueryResponse {
  answer: string;
  citations: QueryCitation[];
}

export interface ApiError {
  detail: string;
}
