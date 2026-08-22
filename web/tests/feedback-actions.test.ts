import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { submitFeedbackAction } from "../app/feedback-actions";
import { personalFetch } from "../lib/personal-opportunities";
import { publicId } from "./personal-fixtures";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: vi.fn() }));
vi.mock("../lib/personal-opportunities", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/personal-opportunities")>();
  return { ...original, personalFetch: vi.fn() };
});

describe("feedback server action", () => {
  beforeEach(() => vi.clearAllMocks());

  it("maps controlled claim server-side and redirects to owner-safe status", async () => {
    vi.mocked(personalFetch).mockResolvedValue({
      feedback: { feedback_event_id: "019b0000-0000-7000-8000-000000000721" },
      evidence: [],
    } as never);
    const data = new FormData();
    data.set("public_id", publicId);
    data.set("ranking_snapshot_id", "019b0000-0000-7000-8000-000000000722");
    data.set("match_snapshot_id", "019b0000-0000-7000-8000-000000000723");
    data.set("opportunity_version", "2");
    data.set("user_state_version", "1");
    data.set("claim_kind", "EXPLANATION_UNCLEAR");
    data.set("user_statement", "解释没有指出证据位置。");
    data.append("evidence_ref_id", "019b0000-0000-7000-8000-000000000724");
    data.set("consent", "on");

    await submitFeedbackAction({ error: null }, data);

    const [path, request] = vi.mocked(personalFetch).mock.calls[0];
    expect(path).toBe(`/api/v1/me/opportunities/${publicId}/feedback`);
    expect(new Headers(request?.headers).get("Idempotency-Key")).toBeTruthy();
    expect(JSON.parse(String(request?.body))).toEqual(
      expect.objectContaining({
        event_type: "EXPLICIT_EVALUATION",
        claim_kind: "EXPLANATION_UNCLEAR",
        structured_reason_code: "MISSING_EVIDENCE_EXPLANATION",
        consent_scope: "FEEDBACK_REVIEW_AND_VALIDATION",
      }),
    );
    expect(revalidatePath).toHaveBeenCalledWith("/me/feedback");
    expect(redirect).toHaveBeenCalledWith(
      "/me/feedback/019b0000-0000-7000-8000-000000000721",
    );
  });

  it("returns an accessible-safe validation error before network access", async () => {
    const data = new FormData();
    data.set("public_id", publicId);
    data.set("claim_kind", "FORGED_RULE_CHANGE");

    await expect(submitFeedbackAction({ error: null }, data)).resolves.toEqual({
      error: "请选择受支持的纠错类型并确认用途授权。",
    });
    expect(personalFetch).not.toHaveBeenCalled();
  });
});
