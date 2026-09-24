"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Document, UserRole } from "@/types";
import { listDocuments } from "@/lib/api/documents";
import { getUser } from "@/lib/api/auth";
import { applicationRoutes } from "@/utils/applicationRoutes";
import { UploadForm } from "@/components/documents/UploadForm";
import { DocumentList } from "@/components/documents/DocumentList";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function DocumentsPage() {
  const router = useRouter();
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const [userRole, setUserRole] = useState<UserRole | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const triggerRefresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  useEffect(() => {
    getUser()
      .then((u) => setUserRole(u.role))
      .catch(() => router.replace(applicationRoutes.login));
  }, [router]);

  useEffect(() => {
    listDocuments()
      .then(setDocuments)
      .catch(() => router.replace(applicationRoutes.login));
  }, [router, refreshKey]);

  if (documents === null || userRole === null) return null;

  return (
    <div className="flex flex-col items-center py-12 px-4 gap-8">
      <div className="w-full max-w-2xl">
        <span className="text-2xl font-semibold">Documents</span>
      </div>

      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle>Upload document</CardTitle>
        </CardHeader>
        <CardContent>
          <UploadForm onUploaded={triggerRefresh} userRole={userRole} />
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
    </div>
  );
}
