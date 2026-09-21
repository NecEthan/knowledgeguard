import type { Document, DocumentVersion } from "@/types";
import { ApiError, httpClient } from "./client";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface DocumentDetail extends Document {
  versions: DocumentVersion[];
}

export interface DocumentUploadedResponse {
  id: string;
  status: string;
}

export async function uploadDocument(
  file: File,
  title: string,
): Promise<DocumentUploadedResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("title", title);

  const res = await fetch(`${API_BASE_URL}/documents`, {
    method: "POST",
    credentials: "include",
    body: form,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore parse errors
    }
    throw new ApiError(res.status, detail);
  }

  return res.json();
}

export async function listDocuments(): Promise<Document[]> {
  return httpClient<Document[]>("/documents");
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  return httpClient<DocumentDetail>(`/documents/${id}`);
}

export async function updateDocument(id: string, title: string): Promise<Document> {
  return httpClient<Document>(`/documents/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/documents/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore parse errors
    }
    throw new ApiError(res.status, detail);
  }
}
