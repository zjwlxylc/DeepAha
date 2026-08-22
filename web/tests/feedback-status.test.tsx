import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FeedbackStatus from "../components/feedback-status";
import type { FeedbackStatusDetail } from "../lib/feedback";

const detail: FeedbackStatusDetail = {
  feedback: {
    feedback_event_id: "019b0000-0000-7000-8000-000000000701",
    opportunity_public_id: "opp_0123456789abcdef0123456789abcdef",
    opportunity_version: 2,
    event_type: "EXPLICIT_EVALUATION",
    claim_kind: "EXPLANATION_UNCLEAR",
    status: "NEEDS_EVIDENCE",
    created_at: "2026-08-22T12:00:00Z",
    status_updated_at: "2026-08-22T12:05:00Z",
  },
  evidence: [
    {
      feedback_evidence_link_id: "019b0000-0000-7000-8000-000000000702",
      evidence_ref_id: "019b0000-0000-7000-8000-000000000703",
      relation: "SUPPORTS",
      note: null,
      created_at: "2026-08-22T12:00:00Z",
    },
  ],
};

describe("feedback public status", () => {
  it("uses public language and omits reviewer confidence and risk", () => {
    render(<FeedbackStatus detail={detail} />);

    expect(screen.getByRole("heading", { name: "需要补充证据" })).toBeVisible();
    expect(screen.getByText(/不会直接修改资格、历史匹配或排序/)).toBeVisible();
    expect(screen.getByText(detail.evidence[0].evidence_ref_id)).toBeVisible();
    expect(document.body.textContent).not.toMatch(/reviewer|审核员|confidence|置信度|risk|风险分/);
  });
});
