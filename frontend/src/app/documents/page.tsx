"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Document, User } from "@/types";
import { getUser, logout } from "@/lib/api/auth";
import { listDocuments } from "@/lib/api/documents";
import { applicationRoutes } from "@/utils/applicationRoutes";
import { UploadForm } from "@/components/documents/UploadForm";
import { DocumentList } from "@/components/documents/DocumentList";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function DocumentsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const triggerRefresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  useEffect(() => {
    getUser()
      .then((u) => { setUser(u); return listDocuments(); })
      .then(setDocuments)
      .catch(() => router.replace(applicationRoutes.login));
  }, [router, refreshKey]);

  async function handleLogout() {
    await logout();
    router.replace(applicationRoutes.login);
  }

  if (documents === null) return null;

  return (
    <main className="flex min-h-screen flex-col items-center py-12 px-4 gap-8">
      <div className="w-full max-w-2xl flex items-center justify-between">
        <span className="text-2xl font-semibold">Documents</span>
        <div className="flex items-center gap-3">
          {user && <span className="text-sm text-muted-foreground">{user.email}</span>}
          <Button variant="outline" onClick={handleLogout}>Sign out</Button>
        </div>
      </div>

      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle>Upload document</CardTitle>
        </CardHeader>
        <CardContent>
          <UploadForm onUploaded={triggerRefresh} />
        </CardContent>
      </Card>

      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle>Your documents</CardTitle>
        </CardHeader>
        <CardContent>
          <DocumentList documents={documents} onDeleted={triggerRefresh} />
        </CardContent>
      </Card>
    </main>
  );
}
