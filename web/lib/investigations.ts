import "server-only";

import { randomUUID } from "node:crypto";
import { cookies } from "next/headers";

import { humanTestFetch, LocalHumanTestApiError } from "./local-human-test";

export interface InvestigationSource {
  source_id: string;
  endpoint_id: string;
  authority_name: string;
  url: string;
  allowed_hosts: string[];
}

export interface InvestigationFact {
  entity_id: string;
  field: string;
  value: string | null;
  status: string;
  note?: string | null;
  evidence: {
    artifact_id: string;
    quote: string;
    locator: Record<string, unknown>;
    sha256: string;
    mechanically_verified: boolean;
  }[];
}

export interface InvestigationTask {
  task_id: string;
  status: string;
  notice_url: string;
  source_id: string;
  endpoint_id: string;
  brief: string;
  created_at: string;
  updated_at: string;
  error_code: string | null;
  calibration: boolean;
  contract_hash: string;
  delivery_hash: string | null;
  issues: string[];
  opportunities: Record<string, unknown> | null;
  facts: InvestigationFact[];
  materials: {
    artifact_id: string;
    url: string;
    sha256: string;
    media_type: string;
    size_bytes: number;
  }[];
  review: { decision: string; reviewer_id: string; reason: string; created_at: string } | null;
}

const registrationConflictCodes = new Set([
  "APPROVED_SOURCE_REQUIRED", "NOTICE_OUTSIDE_APPROVED_HOSTS", "IDEMPOTENCY_CONFLICT",
]);

export class InvestigationApiError extends LocalHumanTestApiError {
  constructor(status: number, public readonly code: string | null) { super(status); }
}

export async function postInvestigation(path: string, body: object): Promise<InvestigationTask> {
  const token = (await cookies()).get("deepaha_phase7_reviewer_session")?.value;
  if (!token) throw new InvestigationApiError(401, null);
  const baseUrl = process.env.DEEPAHA_API_BASE_URL ?? "http://127.0.0.1:8000";
  const response = await fetch(new URL(`/api/v1/local-human-test${path}`, baseUrl), {
    method: "POST", cache: "no-store", redirect: "error",
    headers: {
      Accept: "application/json", "Content-Type": "application/json",
      Authorization: `Bearer ${token}`, "Idempotency-Key": randomUUID(),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let code: string | null = null;
    if (response.status === 409) {
      const detail = await response.json().catch(() => null);
      const candidate: unknown = detail?.detail?.code;
      if (typeof candidate === "string" && registrationConflictCodes.has(candidate)) code = candidate;
    }
    throw new InvestigationApiError(response.status, code);
  }
  return await response.json() as InvestigationTask;
}

export function getInvestigations(): Promise<{ tasks: InvestigationTask[] }> {
  return humanTestFetch("/investigations");
}

export function getInvestigationSources(): Promise<{ sources: InvestigationSource[] }> {
  return humanTestFetch("/investigations/sources");
}

export function getInvestigation(taskId: string): Promise<InvestigationTask> {
  return humanTestFetch(`/investigations/${encodeURIComponent(taskId)}`);
}
