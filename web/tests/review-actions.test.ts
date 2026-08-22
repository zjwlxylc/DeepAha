import { revalidatePath } from "next/cache";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  appendAssessmentAction,
  appendAdjudicationAction,
  createApprovedLabelAction,
} from "../app/review-actions";
import { reviewFetch } from "../lib/review-feedback";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("../lib/review-feedback", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/review-feedback")>();
  return { ...original, reviewFetch: vi.fn() };
});

const caseId = "019b0000-0000-7000-8000-000000000731";
const evidenceId = "019b0000-0000-7000-8000-000000000732";
const assessmentId = "019b0000-0000-7000-8000-000000000733";
const adjudicationId = "019b0000-0000-7000-8000-000000000734";

function baseData(): FormData {
  const data = new FormData();
  data.set("review_case_id", caseId);
  data.append("evidence_ref_id", evidenceId);
  return data;
}

describe("review server actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(reviewFetch).mockResolvedValue({} as never);
  });

  it("uses separate role endpoints without accepting reviewer identity", async () => {
    const assessment = baseData();
    assessment.set("evidence_complete", "on");
    assessment.set("confidence_band", "HIGH");
    assessment.set("risk_level", "NORMAL");
    assessment.set("rationale", "合成审核：证据完整。");
    const adjudication = baseData();
    adjudication.set("confidence_assessment_id", assessmentId);
    adjudication.set("decision", "CONFIRMED");
    adjudication.set("reason", "合成裁决：确认解释问题。");
    const label = baseData();
    label.set("feedback_adjudication_id", adjudicationId);
    label.set("approved_target_value", "解释应明确显示官方证据入口。");

    await appendAssessmentAction({ error: null, message: null }, assessment);
    await appendAdjudicationAction({ error: null, message: null }, adjudication);
    await createApprovedLabelAction({ error: null, message: null }, label);

    expect(vi.mocked(reviewFetch).mock.calls.map(([path]) => path)).toEqual([
      `/api/v1/review/feedback/${caseId}/assessments`,
      `/api/v1/review/feedback/${caseId}/adjudications`,
      `/api/v1/review/feedback/${caseId}/labels`,
    ]);
    for (const [, request] of vi.mocked(reviewFetch).mock.calls) {
      expect(new Headers(request?.headers).get("Idempotency-Key")).toBeTruthy();
      expect(String(request?.body)).not.toMatch(/reviewer_id|adjudicator_id|curator_id/);
    }
    expect(revalidatePath).toHaveBeenCalledWith(`/review/feedback/${caseId}`);
  });

  it("returns a generic role/resource error for reviewer API failures", async () => {
    vi.mocked(reviewFetch).mockRejectedValue(new Error("secret SQL role detail"));
    const data = baseData();
    data.set("confidence_band", "LOW");
    data.set("risk_level", "NORMAL");
    data.set("rationale", "合成审核。 ");

    await expect(
      appendAssessmentAction({ error: null, message: null }, data),
    ).resolves.toEqual({
      error: "当前审核操作未获授权或资源不可用。",
      message: null,
    });
  });
});
