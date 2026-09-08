import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import InvestigationFactReview from "../components/investigations/fact-review";
import type { InvestigationTask } from "../lib/investigations";
import { bindingTarget, task, evidenceCheck, factPreparation, taskId } from "./investigations-fixture";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

function prepared(): InvestigationTask {
  return { ...task, status: "APPROVED", evidence_check: evidenceCheck,
    entity_binding: { binding_id: factPreparation.binding_id, sequence: 1,
      opportunity_id: bindingTarget.opportunity_id, opportunity_version: 1,
      opportunity_public_id: bindingTarget.public_id, opportunity_title: bindingTarget.title,
      source_bundle_revision_id: taskId, canonical_bundle_hash: "a".repeat(64), bundle_status: "FROZEN",
      positions: [], unmapped_position_ids: [], reason: "Synthetic", created_at: task.updated_at },
    fact_review: { current: structuredClone(factPreparation), history: [] },
  };
}

describe("independent field review", () => {
  it("requires explicit decisions and preserves the common evidence dimensions", () => {
    render(<InvestigationFactReview task={prepared()} requestKey={taskId} />);
    expect(screen.getByLabelText("字段决定")).toHaveValue("");
    expect(screen.getByLabelText("原文是否支持该规范值")).toHaveValue("");
    expect(screen.getByLabelText("更正、适用范围与例外核查")).toHaveValue("");
    expect(screen.getByText("内容：找到原文 · 定位：声明定位成立")).toBeVisible();
    expect(screen.queryByRole("button", { name: "保存审核事实集" })).not.toBeInTheDocument();
  });
  it("does not equate found text or an old boolean with verified evidence", () => {
    const current = prepared(), row = current.fact_review!.current!.rows[0];
    row.candidate_id = null; row.abstained = true;
    row.evidence[0].binding = null;
    row.evidence[0].check_reference.verdict = "UNVERIFIED";
    row.evidence[0].check_reference.persistent_binding = null;
    render(<InvestigationFactReview task={current} requestKey={taskId} />);
    expect(screen.getByText(/0 个已接入审核，1 个仍待处理/)).toBeVisible();
    expect(screen.getByText("持久证据：尚未关联 · 待核验")).toBeVisible();
    expect(screen.getByText(/尚未接入审核，保留原始状态/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "记录字段审核" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存审核事实集" })).not.toBeInTheDocument();
  });
  it("requires preparation again when the evidence receipt has changed", () => {
    const current = prepared();
    current.evidence_check = { ...evidenceCheck, check_id: taskId };
    render(<InvestigationFactReview task={current} requestKey={taskId} />);
    expect(screen.getByRole("button", { name: "整理字段候选与证据" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "记录字段审核" })).not.toBeInTheDocument();
  });
  it("keeps pending adjudication recoverable while preserving the previous decision", () => {
    const current = prepared();
    current.fact_review!.current!.decisions[current.fact_review!.current!.rows[0].candidate_id!] = {
      decision_id: taskId, decision: "NEEDS_ADJUDICATION", reason: "合成待核对事项", reviewer_id: taskId, created_at: task.updated_at,
    };
    render(<InvestigationFactReview task={current} requestKey={taskId} />);
    expect(screen.getByText(/审核：需要进一步裁决/)).toBeVisible();
    expect(screen.getByLabelText("字段决定")).toHaveValue("");
    expect(screen.getByRole("button", { name: "记录字段审核" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "保存审核事实集" })).not.toBeInTheDocument();
  });
});
