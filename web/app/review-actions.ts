"use server";

import { randomUUID } from "node:crypto";

import { revalidatePath } from "next/cache";

import { reviewFetch } from "../lib/review-feedback";

export interface ReviewActionState {
  error: string | null;
  message: string | null;
}

function text(formData: FormData, key: string): string {
  return String(formData.get(key) ?? "").trim();
}

function evidenceIds(formData: FormData): string[] {
  return formData.getAll("evidence_ref_id").map(String).filter(Boolean);
}

function validCaseId(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
    value,
  );
}

async function writeReview(
  caseId: string,
  suffix: "assessments" | "adjudications" | "labels",
  body: object,
  success: string,
): Promise<ReviewActionState> {
  if (!validCaseId(caseId)) {
    return { error: "当前审核操作未获授权或资源不可用。", message: null };
  }
  try {
    await reviewFetch(`/api/v1/review/feedback/${caseId}/${suffix}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": randomUUID(),
      },
      body: JSON.stringify(body),
    });
  } catch {
    return { error: "当前审核操作未获授权或资源不可用。", message: null };
  }
  revalidatePath(`/review/feedback/${caseId}`);
  revalidatePath("/review/feedback");
  return { error: null, message: success };
}

export async function appendAssessmentAction(
  _state: ReviewActionState,
  formData: FormData,
): Promise<ReviewActionState> {
  const confidenceBand = text(formData, "confidence_band");
  const riskLevel = text(formData, "risk_level");
  const rationale = text(formData, "rationale");
  if (
    !["LOW", "MEDIUM", "HIGH"].includes(confidenceBand) ||
    !["NORMAL", "HIGH_IMPACT"].includes(riskLevel) ||
    !rationale ||
    rationale.length > 500
  ) {
    return { error: "请完整填写受控评估字段。", message: null };
  }
  return writeReview(
    text(formData, "review_case_id"),
    "assessments",
    {
      evidence_complete: formData.get("evidence_complete") === "on",
      confidence_band: confidenceBand,
      risk_level: riskLevel,
      conflict: formData.get("conflict") === "on",
      evidence_ref_ids: evidenceIds(formData),
      rationale,
    },
    "评估已追加。",
  );
}

export async function appendAdjudicationAction(
  _state: ReviewActionState,
  formData: FormData,
): Promise<ReviewActionState> {
  const decision = text(formData, "decision");
  const reason = text(formData, "reason");
  if (
    !["NEEDS_EVIDENCE", "CONFLICT", "CONFIRMED", "REJECTED"].includes(decision) ||
    !reason ||
    reason.length > 500
  ) {
    return { error: "请完整填写受控裁决字段。", message: null };
  }
  return writeReview(
    text(formData, "review_case_id"),
    "adjudications",
    {
      confidence_assessment_id: text(formData, "confidence_assessment_id"),
      decision,
      evidence_ref_ids: evidenceIds(formData),
      reason,
    },
    "裁决已追加。",
  );
}

export async function createApprovedLabelAction(
  _state: ReviewActionState,
  formData: FormData,
): Promise<ReviewActionState> {
  const target = text(formData, "approved_target_value");
  if (!target || target.length > 500 || evidenceIds(formData).length === 0) {
    return { error: "标签必须包含受控目标和官方证据。", message: null };
  }
  return writeReview(
    text(formData, "review_case_id"),
    "labels",
    {
      feedback_adjudication_id: text(formData, "feedback_adjudication_id"),
      approved_target_value: target,
      evidence_ref_ids: evidenceIds(formData),
    },
    "离线标签资产已创建。",
  );
}
