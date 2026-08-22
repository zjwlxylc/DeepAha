import type {
  PersonalOpportunityDetail,
  PersonalPriorityPage,
} from "../lib/personal-opportunities";
import { publicDetail, publicId } from "./fixtures";

export { publicId };

const matchSnapshotId = "019b0000-0000-7000-8000-000000000611";
const opportunityId = "019b0000-0000-7000-8000-000000000612";
const ruleId = "019b0000-0000-7000-8000-000000000613";
const evidenceId = publicDetail.key_evidence[0].evidence_ref_id;

export const personalPriorityPage: PersonalPriorityPage = {
  ranking_snapshot_id: "019b0000-0000-7000-8000-000000000601",
  omitted_rule_set_count: 0,
  items: [
    {
      ranking: {
        ordinal: 1,
        opportunity_id: opportunityId,
        opportunity_version: 2,
        match_snapshot_id: matchSnapshotId,
        eligibility_status: "ELIGIBLE",
        reason_codes: ["ELIGIBILITY_ELIGIBLE", "PREFERRED_REGION", "EARLIER_DEADLINE"],
        deadline: publicDetail.deadline,
      },
      opportunity: publicDetail,
    },
    {
      ranking: {
        ordinal: 2,
        opportunity_id: "019b0000-0000-7000-8000-000000000614",
        opportunity_version: 1,
        match_snapshot_id: "019b0000-0000-7000-8000-000000000615",
        eligibility_status: "LIKELY_ELIGIBLE",
        reason_codes: ["ELIGIBILITY_LIKELY", "EARLIER_DEADLINE"],
        deadline: "2026-09-25",
      },
      opportunity: {
        ...publicDetail,
        public_id: "opp_abcdefabcdefabcdefabcdefabcdefab",
        title: "合成第二优先机会",
        deadline: "2026-09-25",
      },
    },
  ],
};

export const personalDetail: PersonalOpportunityDetail = {
  opportunity: publicDetail,
  eligibility: {
    snapshot_id: matchSnapshotId,
    opportunity_id: opportunityId,
    opportunity_version: 2,
    rule_set_id: "019b0000-0000-7000-8000-000000000616",
    rule_set_version: 1,
    profile_snapshot_id: "019b0000-0000-7000-8000-000000000617",
    profile_version: 1,
    eligibility_result: {
      result_id: "019b0000-0000-7000-8000-000000000618",
      status: "UNCERTAIN",
      rule_evaluations: [
        {
          rule_id: ruleId,
          outcome: "UNKNOWN",
          deterministic: true,
          official_evidence: true,
          reason_code: "MISSING_PROFILE_FIELD",
          evidence_ref_ids: [evidenceId],
          missing_fields: ["hukou_region"],
        },
      ],
      satisfied_rule_ids: [],
      conflict_rule_ids: [],
      unknown_rule_ids: [ruleId],
      missing_fields: ["hukou_region"],
      review_reasons: ["MISSING_REQUIRED_PROFILE_FIELD"],
      evaluated_at: "2026-08-22T09:00:00Z",
      engine_version: "phase4-eligibility-engine-v1",
    },
    compiler_version: "phase4-rule-compiler-v1",
    engine_version: "phase4-eligibility-engine-v1",
    major_catalog_version: "phase4-synthetic-major-catalog-v1",
    major_mapping_version: "phase4-synthetic-major-mapping-v1",
    scenario_clock: "2026-08-22",
    input_sha256: "6".repeat(64),
    created_at: "2026-08-22T09:00:00Z",
  },
  action: null,
};
