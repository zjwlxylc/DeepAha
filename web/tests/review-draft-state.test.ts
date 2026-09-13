import { describe, expect, it } from "vitest";
import { readReviewDraft, saveReviewDraft, clearReviewDraft } from "../lib/review-draft-state";

describe("review draft memory", () => {
  it("isolates sessions and material versions and clears committed drafts", () => {
    const key = JSON.stringify(["session-a", "task", "material-v1", "candidate"]);
    saveReviewDraft(key, { requestKey: "original-idempotency-key", values: { reason: ["尚未提交"] } });
    expect(readReviewDraft(key)?.values.reason).toEqual(["尚未提交"]);
    expect(readReviewDraft(JSON.stringify(["session-b", "task", "material-v1", "candidate"]))).toBeUndefined();
    expect(readReviewDraft(JSON.stringify(["session-a", "task", "material-v2", "candidate"]))).toBeUndefined();
    clearReviewDraft(key);
    expect(readReviewDraft(key)).toBeUndefined();
  });
});
