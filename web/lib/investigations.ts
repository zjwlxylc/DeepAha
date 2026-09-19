import "server-only";

import { cookies } from "next/headers";

import { humanTestFetch, LocalHumanTestApiError } from "./local-human-test";

export interface InvestigationSource {
  usage_note?: string;
  sample?: { title?: string; brief?: string; expected_artifact_urls?: string[] };
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
    verification?: EvidenceVerification | null;
  }[];
}

export interface EvidenceVerification {
  artifact_id: string; artifact_sha256: string; quote: string;
  original_locator: Record<string, unknown>;
  reader: { name: string; version: string; parse_contract: string; comparison_version: string } | null;
  representation_sha256: string | null; content_support: string; declared_locator: string;
  binding: string; precision: string; verdict: "PASS" | "FAIL" | "UNVERIFIED";
  matches: { projection_id: string; source_spans: { origin_id: string; start: number; end: number }[] }[];
  reason_codes: string[]; verifier_version: string;
}

export interface InvestigationEvidenceCheck {
  check_id: string; input_hash: string; result_hash: string; delivery_hash: string;
  created_at: string; scope: "MECHANICAL_EVIDENCE_ONLY";
  verdict: "PASS" | "FAIL" | "UNVERIFIED";
  counts: Record<"PASS" | "FAIL" | "UNVERIFIED", number>;
  references: {
    fact_index: number; reference_index: number; entity_id: string; field: string; artifact_id: string;
    verification: EvidenceVerification; verdict: "PASS" | "FAIL" | "UNVERIFIED";
    persistent_binding: { document_id: string; document_parse_key: string; parse_attempt_id: string;
      block_id: string; evidence_ref_id: string; evidence_binding_hash: string } | null;
    binding_reason: string | null;
  }[];
}

export interface InvestigationTask {
  rule_review?: { current: InvestigationRulePreparation[]; history: { rule_preparation_id: string; entity_id: string; fact_set_id: string; compiler_version: string; created_at: string }[] };
  fact_review?: { current: InvestigationFactPreparation | null; history: { preparation_id: string; binding_id: string; mapping_version: string; created_at: string }[] };
  evidence_check?: InvestigationEvidenceCheck | null;
  evidence_check_history?: InvestigationEvidenceCheck[];
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
  dispatch_pending?: boolean;
  dispatch_requested_at?: string | null;
  runtime_id?: string | null;
  remote_session_id?: string | null;
  deadline_at?: string | null;
  calibration: boolean;
  contract_hash: string;
  delivery_hash: string | null;
  issues: string[];
  opportunities: Record<string, unknown> | null;
  facts: InvestigationFact[];
  materials: {
    artifact_id: string;
    remote_path?: string;
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
    // Exclusion counters and per-material exclusion state are absent from
    // payloads written before the exclusion flow existed, so they stay optional
    // instead of making older cached preparation reads unrepresentable.
    excluded_count?: number;
    unsupported_count?: number;
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
      excluded?: boolean;
      evidence_mode?: "TEXT" | "OPAQUE_NO_TEXT" | null;
      exclusion?: { reason: string; excluded_by: string; excluded_at: string } | null;
    }[];
  } | null;
}

export interface InvestigationFactPreparation {
  preparation_id: string; binding_id: string; check_id: string; mapping_version: string; result_hash: string;
  targets: { entity_id: string; entity_kind?: string; name: string; target_scope: "OPPORTUNITY" | "UNIT";
    opportunity_id: string; opportunity_version: number; opportunity_unit_id: string | null;
    opportunity_unit_version_id: string | null; extraction_run_id: string | null }[];
  rows: { source_index: number; entity_id: string; original: InvestigationFact;
    original_field: string; field_name: string | null; raw_value: string | null;
    normalized_value_candidate: unknown; abstained: boolean; candidate_id: string | null;
    issue_codes: string[]; evidence: { reference: InvestigationFact["evidence"][number]; check_reference: InvestigationEvidenceCheck["references"][number];
      binding: { block_id: string; evidence_ref_id: string; block_text: string;
        structural_locator: Record<string, unknown> } | null }[] }[];
  decisions: Record<string, { decision_id: string; decision: string; reason: string; reviewer_id: string; created_at: string }>;
  promotions: Record<string, { fact_set_id: string; status: string; reason: string }>;
  active_fact_sets: Record<string, { fact_set_id: string; version: number; source_bundle_revision_id: string }>;
}

export interface InvestigationRuleAssessment {
  evidence_ref_id: string; authority: string | null; relation: string | null; effective_at: string | null;
  applicability: string; reason: string;
}

export interface InvestigationRuleDecision {
  decision_id: string; rule_candidate_id: string; decision: string; reason: string;
  evidence: InvestigationRuleAssessment[]; reviewer_id: string; created_at: string;
}

export interface InvestigationRulePreparation {
  rule_preparation_id: string; fact_preparation_id: string; fact_set_id: string; entity_id: string;
  binding_id: string; delivery_hash: string; check_id: string; compiler_version: string; result_hash: string;
  fact_preparation_hash: string; fact_set_version: number; source_bundle_revision_id: string; scope_status: string;
  target: InvestigationFactPreparation["targets"][number]; source_rows: InvestigationFactPreparation["rows"];
  rows: { verified_fact_id: string; candidate_id: string; field_name: string; fact_state: string;
    normalized_value: unknown; rule_candidate_id: string | null; reason_code: string;
    payload: { field: string; operator: string; value_type: string; value: unknown; code: string } | null;
    evidence_ref_ids: string[]; evidence: { evidence_ref_id: string; document_id: string; block_id: string;
      text: string; structural_locator: Record<string, unknown> }[] }[];
  decisions: Record<string, InvestigationRuleDecision>; decision_history: InvestigationRuleDecision[];
}

export interface InvestigationBindingTarget {
  opportunity_id: string; public_id: string; version: number; title: string;
  positions: { unit_id: string; version_id: string; public_id: string; key: string; label: string }[];
}

export function getInvestigationBindingTargets(): Promise<{ targets: InvestigationBindingTarget[] }> {
  return humanTestFetch("/investigations/binding-targets");
}

const registrationConflictCodes = new Set([
  "RULE_EVIDENCE_REVIEW_INCOMPLETE", "RULE_NOT_EXECUTABLE", "RULE_CANDIDATE_ALREADY_DECIDED",
  "REGISTRATION_EXISTING_IDENTITY_OR_REVIEW_REQUIRED", "REGISTRATION_POSITION_INVALID", "REGISTRATION_POSITION_KEY_CONFLICT",
  "FACT_EVIDENCE_CHECK_REFRESH_REQUIRED", "FACT_BINDING_DOCUMENTS_CHANGED", "FACT_ALL_CANDIDATES_REQUIRE_DECISION",
  "APPROVED_SOURCE_REQUIRED", "NOTICE_OUTSIDE_APPROVED_HOSTS", "IDEMPOTENCY_CONFLICT",
]);

// 409 codes a dispatch request can return. Kept separate from registration conflicts
// so the shared `postInvestigation` reader can surface them without widening the
// registration-specific list.
const dispatchConflictCodes = new Set(["TASK_NOT_DISPATCHABLE", "TASK_ALREADY_RUNNING"]);

// 409 codes the document-exclusion endpoints return. They need their own list so
// the shared `postInvestigation` reader keeps the code: without it the operator
// only sees the generic "refresh the page" copy for a reason they can act on.
const documentExclusionConflictCodes = new Set([
  "DOCUMENT_EXCLUSION_REASON_REQUIRED", "DOCUMENT_EXCLUSION_NOT_UNSUPPORTED", "DOCUMENT_EXCLUSION_NOT_ALLOWED",
  "DOCUMENT_EXCLUSION_ALREADY_PRESENT", "DOCUMENT_EXCLUSION_NOT_FOUND", "DOCUMENT_EXCLUSION_DELIVERY_CONFLICT",
  "DOCUMENT_EXCLUSION_MATERIAL_NOT_FOUND",
]);

export class InvestigationApiError extends LocalHumanTestApiError {
  constructor(status: number, public readonly code: string | null) { super(status); }
}

export async function postInvestigation<T = InvestigationTask>(path: string, body: object, requestKey: string): Promise<T> {
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
      if (typeof candidate === "string" && (registrationConflictCodes.has(candidate)
        || dispatchConflictCodes.has(candidate) || documentExclusionConflictCodes.has(candidate))) code = candidate;
    }
    throw new InvestigationApiError(response.status, code);
  }
  return await response.json() as T;
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
