import { render, screen } from "@testing-library/react";
import { cookies } from "next/headers";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ReviewQueuePage from "../app/review/feedback/page";
import ReviewQueueError from "../app/review/feedback/error";
import ReviewQueueLoading from "../app/review/feedback/loading";
import ReviewCaseError from "../app/review/feedback/[caseId]/error";
import ReviewCaseLoading from "../app/review/feedback/[caseId]/loading";
import ReviewCasePanel from "../components/review-case-panel";
import {
  getReviewQueue,
  reviewFetch,
  type ReviewCaseDetail,
} from "../lib/review-feedback";

vi.mock("next/headers", () => ({ cookies: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("../lib/review-feedback", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/review-feedback")>();
  return { ...original, getReviewQueue: vi.fn() };
});

const caseDetail: ReviewCaseDetail = {
  case: {
    review_case_id: "019b0000-0000-7000-8000-000000000711",
    feedback_event_id: "019b0000-0000-7000-8000-000000000712",
    version: 1,
    status: "RECEIVED",
    priority: 3,
    due_at: "2026-08-24T12:00:00Z",
    overdue: false,
    claim_kind: "EXPLANATION_UNCLEAR",
    opportunity_public_id: "opp_0123456789abcdef0123456789abcdef",
    opportunity_title: "合成青年人才补贴计划",
    opportunity_version: 2,
    created_at: "2026-08-22T12:00:00Z",
  },
  user_statement: "合成反馈：解释没有展示证据位置。",
  structured_reason_code: "MISSING_EVIDENCE_EXPLANATION",
  match_snapshot_id: "019b0000-0000-7000-8000-000000000713",
  history: [
    {
      version: 1,
      status: "RECEIVED",
      priority: 3,
      due_at: "2026-08-24T12:00:00Z",
      transition_reason: "INITIAL_SUBMISSION",
      created_at: "2026-08-22T12:00:00Z",
    },
  ],
  evidence: [
    {
      evidence_ref_id: "019b0000-0000-7000-8000-000000000714",
      document_id: "019b0000-0000-7000-8000-000000000715",
      locator_kind: "html_selector",
      locator_value: "main article",
      relation: "SUPPORTS",
      actor_kind: "USER",
      note: null,
      created_at: "2026-08-22T12:00:00Z",
    },
  ],
  latest_assessment: null,
  latest_adjudication: null,
  approved_label_id: null,
};

describe("controlled reviewer flow", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders only case evidence, history and native assessment/adjudication controls", () => {
    render(<ReviewCasePanel detail={caseDetail} />);

    expect(screen.getByRole("heading", { name: "合成青年人才补贴计划" })).toBeVisible();
    expect(screen.getByText(caseDetail.match_snapshot_id)).toBeVisible();
    expect(screen.getByText(caseDetail.evidence[0].evidence_ref_id)).toBeVisible();
    expect(screen.getByLabelText("证据完整")).toBeInstanceOf(HTMLInputElement);
    expect(screen.getByLabelText("置信区间")).toBeInstanceOf(HTMLSelectElement);
    expect(screen.getByRole("button", { name: "追加评估" })).toBeVisible();
    expect(screen.getByText(/完成评估后才能裁决/)).toBeVisible();
    expect(document.body.textContent).not.toMatch(/仪表盘|批量|用户搜索|部署|模型控制/);
  });

  it("keeps the reviewer cookie separate and server-only", async () => {
    vi.mocked(cookies).mockResolvedValue({
      get: (name: string) =>
        name === "deepaha_phase7_reviewer_session"
          ? { value: "reviewer-session-secret" }
          : undefined,
    } as Awaited<ReturnType<typeof cookies>>);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await reviewFetch("/api/v1/review/feedback");

    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get("Authorization")).toBe(
      "Bearer reviewer-session-secret",
    );
    expect(document.body.textContent).not.toContain("reviewer-session-secret");
  });

  it("shows a finite queue without adding an admin dashboard", async () => {
    vi.mocked(getReviewQueue).mockResolvedValue({ items: [caseDetail.case] });

    render(await ReviewQueuePage());

    expect(screen.getByRole("heading", { name: "反馈审核队列" })).toBeVisible();
    expect(screen.getByRole("link", { name: /合成青年人才补贴计划/ })).toHaveAttribute(
      "href",
      `/review/feedback/${caseDetail.case.review_case_id}`,
    );
    expect(document.body.textContent).not.toMatch(/运营后台|数据看板|批量裁决/);
  });

  it("announces loading and generic role/resource failures without exception detail", () => {
    const { rerender } = render(<ReviewQueueLoading />);
    expect(screen.getByRole("status")).toHaveTextContent("正在读取受控审核队列");
    rerender(<ReviewCaseLoading />);
    expect(screen.getByRole("status")).toHaveTextContent("正在读取反馈案件");
    rerender(<ReviewQueueError reset={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("审核队列不可用");
    rerender(<ReviewCaseError reset={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("反馈案件不可用");
    expect(document.body.textContent).not.toMatch(/sql|token|case exists/i);
  });
});
