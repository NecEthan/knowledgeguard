"use client";

import { useRef, useState } from "react";
import { uploadDocument } from "@/lib/api/documents";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface UploadFormProps {
  onUploaded: () => void;
}

export function UploadForm({ onUploaded }: UploadFormProps) {
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError(null);
    setLoading(true);
    try {
      await uploadDocument(file, title || file.name);
      setTitle("");
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      onUploaded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="upload-title">Title</Label>
        <Input
          id="upload-title"
          type="text"
          placeholder="Leave blank to use filename"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="upload-file">File</Label>
        <Input
          id="upload-file"
          type="file"
          accept=".pdf,.docx,.txt"
          required
          ref={fileRef}
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>

      <Button type="submit" disabled={loading || !file}>
        {loading ? "Uploading…" : "Upload document"}
      </Button>
    </form>
  );
}
