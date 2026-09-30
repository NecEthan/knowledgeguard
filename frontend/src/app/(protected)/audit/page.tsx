"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { AuditEvent } from "@/types";
import { listAuditEvents } from "@/lib/api/audit";
import { getUser } from "@/lib/api/auth";
import { applicationRoutes } from "@/utils/applicationRoutes";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AuditPage() {
  const router = useRouter();
  const [events, setEvents] = useState<AuditEvent[] | null>(null);

  useEffect(() => {
    getUser()
      .then((u) => {
        if (u.role !== "admin") {
          router.replace(applicationRoutes.documents);
          return;
        }
        return listAuditEvents();
      })
      .then((data) => {
        if (data) setEvents(data);
      })
      .catch(() => router.replace(applicationRoutes.login));
  }, [router]);

  if (events === null) return null;

  return (
    <div className="flex flex-col items-center py-12 px-4 gap-8">
      <div className="w-full max-w-4xl">
        <span className="text-2xl font-semibold">Audit Log</span>
      </div>

      <Card className="w-full max-w-4xl">
        <CardHeader>
          <CardTitle>Events</CardTitle>
        </CardHeader>
        <CardContent>
          {events.length === 0 ? (
            <p className="text-sm text-muted-foreground">No audit events yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 pr-4 font-medium">Timestamp</th>
                    <th className="pb-2 pr-4 font-medium">Event</th>
                    <th className="pb-2 pr-4 font-medium">User ID</th>
                    <th className="pb-2 pr-4 font-medium">Document ID</th>
                    <th className="pb-2 font-medium">Metadata</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event) => (
                    <tr key={event.id} className="border-b last:border-0">
                      <td className="py-2 pr-4 whitespace-nowrap font-mono text-xs">
                        {new Date(event.created_at).toLocaleString()}
                      </td>
                      <td className="py-2 pr-4 font-medium">{event.event_type}</td>
                      <td className="py-2 pr-4 font-mono text-xs text-muted-foreground truncate max-w-[120px]">
                        {event.user_id ?? "—"}
                      </td>
                      <td className="py-2 pr-4 font-mono text-xs text-muted-foreground truncate max-w-[120px]">
                        {event.document_id ?? "—"}
                      </td>
                      <td className="py-2 text-xs text-muted-foreground">
                        {event.metadata_
                          ? JSON.stringify(event.metadata_)
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
