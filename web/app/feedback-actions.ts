"use server";

import { randomUUID } from "node:crypto";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import type { FeedbackClaimKind, FeedbackStatusDetail } from "../lib/feedback";
import { personalFetch } from "../lib/personal-opportunities";

export interface FeedbackActionState {
  error: string | null;
}

const claimConfiguration: Record<
  FeedbackClaimKind,
  { eventType: "STRUCTURED_CORRECTION" | "EXPLICIT_EVALUATION"; reasonCode: string }
> = {
  ELIGIBILITY_CORRECTION: {
    eventType: "STRUCTURED_CORRECTION",
    reasonCode: "ELIGIBILITY_RESULT_INCORRECT",
  },
  OPPORTUNITY_FACT_CORRECTION: {
    eventType: "STRUCTURED_CORRECTION",
    reasonCode: "OPPORTUNITY_FACT_OUTDATED",
  },
  EXPLANATION_UNCLEAR: {
    eventType: "EXPLICIT_EVALUATION",
    reasonCode: "MISSING_EVIDENCE_EXPLANATION",
  },
  RANKING_IRRELEVANT: {
    eventType: "EXPLICIT_EVALUATION",
    reasonCode: "RANKING_CONTEXT_IRRELEVANT",
  },
};

function text(formData: FormData, key: string): string {
  return String(formData.get(key) ?? "").trim();
}

function positiveInteger(value: string): number | null {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

export async function submitFeedbackAction(
  _state: FeedbackActionState,
  formData: FormData,
): Promise<FeedbackActionState> {
  const publicId = text(formData, "public_id");
  const claimKind = text(formData, "claim_kind") as FeedbackClaimKind;
  const configuration = claimConfiguration[claimKind];
  const opportunityVersion = positiveInteger(text(formData, "opportunity_version"));
  const userStateVersion = positiveInteger(text(formData, "user_state_version"));
  if (
    !/^opp_[0-9a-f]{32}$/.test(publicId) ||
    !configuration ||
    formData.get("consent") !== "on" ||
    opportunityVersion === null ||
    userStateVersion === null
  ) {
    return { error: "请选择受支持的纠错类型并确认用途授权。" };
  }
  const statement = text(formData, "user_statement");
  if (statement.length > 500) {
    return { error: "补充说明不能超过 500 个字符。" };
  }
  const body = {
    ranking_snapshot_id: text(formData, "ranking_snapshot_id"),
    match_snapshot_id: text(formData, "match_snapshot_id"),
    opportunity_version: opportunityVersion,
    user_state_version: userStateVersion,
    event_type: configuration.eventType,
    claim_kind: claimKind,
    user_statement: statement || null,
    structured_reason_code: configuration.reasonCode,
    initial_evidence_ref_ids: formData
      .getAll("evidence_ref_id")
      .map(String)
      .filter(Boolean),
    consent_version: "phase7-feedback-consent-v1",
    consent_scope: "FEEDBACK_REVIEW_AND_VALIDATION",
  };
  let result: FeedbackStatusDetail;
  try {
    result = await personalFetch<FeedbackStatusDetail>(
      `/api/v1/me/opportunities/${publicId}/feedback`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": randomUUID(),
        },
        body: JSON.stringify(body),
      },
    );
  } catch {
    return { error: "纠错暂时无法提交，请核对当前个人会话和版本后重试。" };
  }
  revalidatePath("/me/feedback");
  revalidatePath(`/me/opportunities/${publicId}`);
  redirect(`/me/feedback/${result.feedback.feedback_event_id}`);
}
