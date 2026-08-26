import "server-only";

import { cookies } from "next/headers";

export interface ProviderStatus {
  configured: boolean;
  provider: string | null;
  base_url: string | null;
  protocol: string | null;
  model_id: string | null;
  model_snapshot: string | null;
  provider_region: string | null;
  zero_retention: boolean | null;
  training_use: boolean | null;
  supports_idempotency: boolean | null;
  egress_ready: boolean;
  updated_at: string | null;
}

export interface LocalSource {
  recipe_id: string;
  source_id: string;
  endpoint_id: string;
  authority_name: string;
  jurisdiction: string | null;
  usage_role: string;
  official_url: string;
  official_host: string;
  verified_at: string;
  maximum_requests: number;
  opportunity_type_hint: string;
}

export interface LocalRun {
  run_id: string;
  mode: "LIVE_OFFICIAL" | "OFFICIAL_REPLAY";
  recipe_ids: string[];
  provider: string;
  model_id: string;
  model_snapshot: string;
  budget: Record<string, unknown>;
  status: string;
  official_request_count: number;
  llm_call_count: number;
  terminal_reason_code: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface LocalItem {
  item_id: string;
  run_id: string;
  recipe_id: string;
  status: string;
  error_code: string | null;
  source_id: string | null;
  endpoint_id: string | null;
  document_id: string | null;
  opportunity_id: string | null;
  model_call_id: string | null;
  verified_fact_set_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ModelAttemptAudit {
  attempt_number: number;
  outcome: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  cost_status: string | null;
  monetary_cost: string | number | null;
}

export interface FactEvidenceBlock {
  evidence_ref_id: string;
  block_id: string;
  document_id: string;
  block_type: string;
  canonical_text_or_value: string;
  structural_locator: Record<string, unknown>;
  source_tier: string;
  source_url: string;
}

export interface FactCandidate {
  candidate_id: string;
  field_name: string;
  raw_value: unknown;
  normalized_value_candidate: unknown;
  confidence: number | null;
  abstained: boolean;
  candidate_reason_code: string;
  decision: string | null;
  evidence: FactEvidenceBlock[];
}

export interface RuleCandidate {
  rule_candidate_id: string;
  proposed_rule_payload: Record<string, unknown>;
  decision: string | null;
}

export interface PublicationPreview {
  item_id: string;
  opportunity_id: string;
  base_version: number;
  approved_field_names: string[];
  missing_field_names: string[];
  content_use_basis: string | null;
  official_evidence_complete: boolean;
  eligibility_ceiling: string;
  blocker_codes: string[];
  eligible: boolean;
}

export interface LocalItemDetail {
  item: LocalItem;
  model_audit: {
    model_call_id: string;
    canonical_request_hash: string;
    canonical_message_hashes: string[];
    actual_payload_hash: string | null;
    egress_decision: string;
    final_status: string | null;
    terminal_disposition: string | null;
    attempts: ModelAttemptAudit[];
  } | null;
  candidates: FactCandidate[];
  rules: RuleCandidate[];
  publication_preview: PublicationPreview | null;
}

export class LocalHumanTestApiError extends Error {
  constructor(public readonly status: number) {
    super("Local human test request failed");
    this.name = "LocalHumanTestApiError";
  }
}

export async function humanTestFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = (await cookies()).get("deepaha_phase7_reviewer_session")?.value;
  if (!token) throw new LocalHumanTestApiError(401);
  const baseUrl = process.env.DEEPAHA_API_BASE_URL ?? "http://127.0.0.1:8000";
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(
    new URL(`/api/v1/local-human-test${path}`, baseUrl),
    { ...init, cache: "no-store", headers },
  );
  if (!response.ok) throw new LocalHumanTestApiError(response.status);
  return (await response.json()) as T;
}

export function getLocalProviderStatus(): Promise<ProviderStatus> {
  return humanTestFetch("/config/provider");
}

export function getLocalSources(): Promise<LocalSource[]> {
  return humanTestFetch("/sources");
}

export function getLocalRuns(): Promise<LocalRun[]> {
  return humanTestFetch("/runs");
}

export function getLocalRun(runId: string): Promise<{ run: LocalRun; items: LocalItem[] }> {
  return humanTestFetch(`/runs/${encodeURIComponent(runId)}`);
}

export function getLocalItem(itemId: string): Promise<LocalItemDetail> {
  return humanTestFetch(`/items/${encodeURIComponent(itemId)}`);
}
