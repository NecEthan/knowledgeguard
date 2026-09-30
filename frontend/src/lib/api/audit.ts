import { httpClient } from "./client";
import type { AuditEvent } from "@/types";

export async function listAuditEvents(): Promise<AuditEvent[]> {
  return httpClient<AuditEvent[]>("/audit");
}
