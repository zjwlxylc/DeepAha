import "server-only";

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
  binding_history?: NonNullable<InvestigationTask["entity_binding"]>[];
  binding_entities?: { id: string; name: string; kind: string; code?: string }[];
  entity_binding?: {
    binding_id: string; sequence: number; opportunity_id: string; opportunity_version: number;
    opportunity_public_id: string; opportunity_title: string; bundle_status: string;
    source_bundle_revision_id: string; canonical_bundle_hash: string;
    positions: { entity_id: string; opportunity_unit_id: string; opportunity_unit_version_id: string }[];
    unmapped_position_ids: string[]; reason: string; created_at: string;
  } | null;
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
  document_preparation?: {
    scope: "DOCUMENT_EVIDENCE_ONLY";
    status: string;
    material_count: number;
    prepared_count: number;
    materials: {
      material_id: string;
      outcome: string;
      error_code: string | null;
      document_id: string | null;
      document_parse_key: string | null;
      parser_name: string | null;
      parser_version: string | null;
      parse_contract_version: string | null;
      block_count: number;
      evidence_ref_count: number;
    }[];
  } | null;
}

export interface InvestigationBindingTarget {
  opportunity_id: string; public_id: string; version: number; title: string;
  positions: { unit_id: string; version_id: string; public_id: string; key: string; label: string }[];
}

export function getInvestigationBindingTargets(): Promise<{ targets: InvestigationBindingTarget[] }> {
  return humanTestFetch("/investigations/binding-targets");
}

const registrationConflictCodes = new Set([
  "APPROVED_SOURCE_REQUIRED", "NOTICE_OUTSIDE_APPROVED_HOSTS", "IDEMPOTENCY_CONFLICT",
]);

export class InvestigationApiError extends LocalHumanTestApiError {
  constructor(status: number, public readonly code: string | null) { super(status); }
}

export async function postInvestigation(path: string, body: object, requestKey: string): Promise<InvestigationTask> {
  const token = (await cookies()).get("deepaha_phase7_reviewer_session")?.value;
  if (!token) throw new InvestigationApiError(401, null);
  const baseUrl = process.env.DEEPAHA_API_BASE_URL ?? "http://127.0.0.1:8000";
  const response = await fetch(new URL(`/api/v1/local-human-test${path}`, baseUrl), {
    method: "POST", cache: "no-store", redirect: "error",
    headers: {
      Accept: "application/json", "Content-Type": "application/json",
      Authorization: `Bearer ${token}`, "Idempotency-Key": requestKey,
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
