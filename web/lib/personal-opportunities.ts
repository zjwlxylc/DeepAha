import "server-only";

import { cookies } from "next/headers";

import type {
  PublicEvidence,
  PublicOpportunityCard,
  PublicOpportunityDetail,
} from "./public-opportunities";

export type EligibilityStatus =
  | "ELIGIBLE"
  | "LIKELY_ELIGIBLE"
  | "UNCERTAIN"
  | "INELIGIBLE";

export interface RuleEvaluation {
  rule_id: string;
  outcome: "SATISFIED" | "CONFLICT" | "UNKNOWN";
  deterministic: boolean;
  official_evidence: boolean;
  reason_code: string;
  evidence_ref_ids: string[];
  missing_fields: string[];
}

export interface MatchSnapshot {
  snapshot_id: string;
  opportunity_id: string;
  opportunity_version: number;
  rule_set_id: string;
  rule_set_version: number;
  profile_snapshot_id: string;
  profile_version: number;
  eligibility_result: {
    result_id: string;
    status: EligibilityStatus;
    rule_evaluations: RuleEvaluation[];
    satisfied_rule_ids: string[];
    conflict_rule_ids: string[];
    unknown_rule_ids: string[];
    missing_fields: string[];
    review_reasons: string[];
    evaluated_at: string;
    engine_version: string;
  };
  compiler_version: string;
  engine_version: string;
  major_catalog_version: string;
  major_mapping_version: string;
  scenario_clock: string;
  input_sha256: string;
  created_at: string;
}

export interface UserStateSnapshot {
  user_state_snapshot_id: string;
  user_state_id: string;
  version: number;
  qualification_profile_snapshot_id: string;
  qualification_profile_version: number;
  life_stage: string | null;
  goal_types: string[];
  attributes: {
    education_level: string | null;
    major_name: string | null;
    major_code: string | null;
    graduation_year: number | null;
    student_status: string | null;
    birth_date: string | null;
    hukou_region: string | null;
    residence_region: string | null;
    target_regions: string[] | null;
    certificates: string[] | null;
  };
  preference_regions: string[];
  preference_types: string[];
  skipped_fields: string[];
  personalization_enabled: boolean;
  consent_version: string;
  allowed_purposes: string[];
  scenario_clock: string;
  input_sha256: string;
  created_at: string;
}

export interface PersonalRankingItem {
  ordinal: number;
  opportunity_id: string;
  opportunity_version: number;
  match_snapshot_id: string;
  eligibility_status: EligibilityStatus;
  reason_codes: string[];
  deadline: string;
}

export interface PersonalPriorityItem {
  ranking: PersonalRankingItem;
  opportunity: PublicOpportunityCard;
}

export interface PersonalPriorityPage {
  ranking_snapshot_id: string;
  items: PersonalPriorityItem[];
  omitted_rule_set_count: number;
}

export interface MaterialPlanItem {
  material_item_id: string;
  label: string;
  completed: boolean;
  due_on: string | null;
}

export interface PersonalActionSnapshot {
  action_snapshot_id: string;
  action_id: string;
  version: number;
  opportunity_id: string;
  opportunity_version: number;
  saved: boolean;
  state: "NOT_STARTED" | "PREPARING" | "APPLIED" | "COMPLETED" | "DISMISSED";
  material_items: MaterialPlanItem[];
  last_event_id: string;
  input_sha256: string;
  created_at: string;
}

export interface PersonalOpportunityDetail {
  opportunity: PublicOpportunityDetail;
  eligibility: MatchSnapshot;
  action: PersonalActionSnapshot | null;
}

export interface OfficialLinkResult {
  official_url: string;
  action: PersonalActionSnapshot;
  event: {
    event_id: string;
    action_id: string;
    action_snapshot_id: string;
    event_type: "OFFICIAL_LINK_OPENED";
    payload_sha256: string;
    occurred_at: string;
  };
}

export class PersonalApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "PersonalApiError";
  }
}

export async function personalFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = (await cookies()).get("deepaha_phase6_session")?.value;
  if (!token) {
    throw new PersonalApiError(401, "Personal session required");
  }
  const baseUrl = process.env.DEEPAHA_API_BASE_URL ?? "http://127.0.0.1:8000";
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(new URL(path, baseUrl), {
    ...init,
    cache: "no-store",
    headers,
  });
  if (!response.ok) {
    throw new PersonalApiError(response.status, "Personal opportunity request failed");
  }
  return (await response.json()) as T;
}

export function getPersonalProfile(): Promise<UserStateSnapshot> {
  return personalFetch<UserStateSnapshot>("/api/v1/me/profile");
}

export function getPersonalPriorities(): Promise<PersonalPriorityPage> {
  return personalFetch<PersonalPriorityPage>("/api/v1/me/opportunities");
}

export function getPersonalOpportunity(publicId: string): Promise<PersonalOpportunityDetail> {
  return personalFetch<PersonalOpportunityDetail>(
    `/api/v1/me/opportunities/${encodeURIComponent(publicId)}`,
  );
}

export type { PublicEvidence };
