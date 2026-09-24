"use client";

import Link from "next/link";
import { useState } from "react";
import type { Document } from "@/types";
import { deleteDocument } from "@/lib/api/documents";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface DocumentListProps {
  documents: Document[];
  onDeleted: () => void;
}

export function DocumentList({ documents, onDeleted }: DocumentListProps) {
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function handleDelete(id: string) {
    setError(null);
    setDeletingId(id);
    try {
      await deleteDocument(id);
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
    } finally {
      setDeletingId(null);
    }
  }

  if (documents.length === 0) {
    return <span className="text-sm text-muted-foreground">No documents yet.</span>;
  }

  return (
    <div className="flex flex-col gap-3">
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {documents.map((doc) => (
        <div
          key={doc.id}
          data-testid="document-row"
          className="flex items-center justify-between rounded-lg border px-4 py-3"
        >
          <div className="flex flex-col gap-0.5">
            <span className="font-medium">{doc.title}</span>
            <span className="text-xs text-muted-foreground">
              {new Date(doc.created_at).toLocaleDateString()}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Link href={`/documents/${doc.id}/versions`}>
              <Button variant="outline" size="sm">
                Versions
              </Button>
            </Link>
            <Button
              variant="destructive"
              size="sm"
              disabled={deletingId === doc.id}
              onClick={() => handleDelete(doc.id)}
            >
              {deletingId === doc.id ? "Deleting…" : "Delete"}
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}
