"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import type { DocumentVersion } from "@/types";
import {
  listDocumentVersions,
  uploadDocumentVersion,
} from "@/lib/api/documents";
import { ApiError } from "@/lib/api/client";
import { applicationRoutes } from "@/utils/applicationRoutes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const STATUS_STYLES: Record<string, string> = {
  ACTIVE: "bg-green-100 text-green-800",
  PROCESSING: "bg-yellow-100 text-yellow-800",
  SUPERSEDED: "bg-gray-100 text-gray-500",
  FAILED: "bg-red-100 text-red-700",
  DELETED: "bg-gray-100 text-gray-400",
  REVIEW_REQUIRED: "bg-orange-100 text-orange-800",
};

export default function VersionHistoryPage() {
  const params = useParams<{ id: string }>();
  const documentId = params.id;
  const router = useRouter();

  const [versions, setVersions] = useState<DocumentVersion[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadVersions = useCallback(() => {
    listDocumentVersions(documentId)
      .then(setVersions)
      .catch(() => router.replace(applicationRoutes.documents));
  }, [documentId, router]);

  useEffect(() => {
    loadVersions();
  }, [loadVersions]);

  async function handleUploadVersion(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      await uploadDocumentVersion(documentId, file);
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      loadVersions();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  if (versions === null) return null;

  return (
    <div className="flex flex-col items-center py-12 px-4 gap-8">
      <div className="w-full max-w-2xl flex items-center justify-between">
        <span className="text-2xl font-semibold">Version History</span>
        <Button
          variant="outline"
          onClick={() => router.push(applicationRoutes.documents)}
        >
          Back to documents
        </Button>
      </div>

      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle>Upload new version</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleUploadVersion} className="flex flex-col gap-4">
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="version-file">File</Label>
              <Input
                id="version-file"
                type="file"
                accept=".pdf,.docx,.txt"
                required
                ref={fileRef}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>
            <Button type="submit" disabled={uploading || !file}>
              {uploading ? "Uploading…" : "Upload new version"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle>Versions</CardTitle>
        </CardHeader>
        <CardContent>
          {versions.length === 0 ? (
            <span className="text-sm text-muted-foreground">No versions yet.</span>
          ) : (
            <div className="flex flex-col gap-3">
              {versions.map((v) => (
                <div
                  key={v.id}
                  data-testid="version-row"
                  className={`flex items-center justify-between rounded-lg border px-4 py-3 ${
                    v.status === "ACTIVE" ? "border-green-400" : ""
                  }`}
                >
                  <div className="flex flex-col gap-0.5">
                    <span className="font-medium">v{v.version_number}</span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(v.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <span
                    data-testid="version-status"
                    className={`text-xs font-semibold rounded px-2 py-1 ${
                      STATUS_STYLES[v.status] ?? "bg-gray-100 text-gray-600"
                    }`}
                  >
                    {v.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
