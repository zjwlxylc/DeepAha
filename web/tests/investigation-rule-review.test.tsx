import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import InvestigationRuleReview from "../components/investigations/rule-review";
import { ruleReadyTask, taskId } from "./investigations-fixture";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

describe("independent rule review", () => {
  it("starts evidence assessment empty and preserves the original quote and shared receipt", () => {
    render(<InvestigationRuleReview task={ruleReadyTask()} requestKey={taskId} />);
    for (const name of ["规则决定", "证据权威级别", "与拟规则的关系", "是否适用于此目标", "证据生效时间（含时区）"]) {
      expect(screen.getByLabelText(name)).toHaveValue("");
    }
    expect(screen.getByText("内容：找到原文 · 定位：声明定位成立")).toBeVisible();
    expect(screen.getByText("拟采用条件：学历 不低于 硕士")).toBeVisible();
    expect(screen.getByRole("link", { name: /下载原件/ })).toBeVisible();
    expect(screen.getByText(/完整条件覆盖/)).toBeVisible();
  });
  it("shows unknown and unprocessed source rows without executable candidates", () => {
    const task = ruleReadyTask(), prep = task.rule_review!.current[0];
    prep.rows[0].fact_state = "UNKNOWN"; prep.rows[0].rule_candidate_id = null; prep.rows[0].payload = null;
    prep.rows[0].reason_code = "FACT_UNKNOWN";
    prep.source_rows.push({ ...structuredClone(prep.source_rows[0]), source_index: 1, candidate_id: null, original_field: "户籍", issue_codes: ["FIELD_UNSUPPORTED"] });
    render(<InvestigationRuleReview task={task} requestKey={taskId} />);
    expect(screen.getByText(/全调查 2 个原始字段/)).toBeVisible();
    expect(screen.getByText(/事实保留未知，不能形成可执行规则/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "记录规则审核" })).not.toBeInTheDocument();
  });
  it.each(["receipt", "facts", "binding", "fact_set"])("disables stale rules when %s changes", kind => {
    const task = ruleReadyTask();
    if (kind === "receipt") task.evidence_check!.check_id = taskId;
    if (kind === "facts") task.fact_review!.current!.preparation_id = taskId;
    if (kind === "binding") task.entity_binding!.binding_id = taskId;
    if (kind === "fact_set") task.fact_review!.current!.active_fact_sets["position-1"].fact_set_id = taskId;
    render(<InvestigationRuleReview task={task} requestKey={taskId} />);
    expect(screen.queryByRole("button", { name: "记录规则审核" })).not.toBeInTheDocument();
  });
  it.each(["NEEDS_ADJUDICATION", "APPROVE", "REJECT"])("retains %s and allows only pending to receive a new decision", decision => {
    const task = ruleReadyTask(), prep = task.rule_review!.current[0];
    const record = { decision_id: taskId, rule_candidate_id: prep.rows[0].rule_candidate_id!, decision,
      reason: "合成审核记录", evidence: [], reviewer_id: taskId, created_at: task.updated_at };
    prep.decisions[record.rule_candidate_id] = record; prep.decision_history.push(record);
    render(<InvestigationRuleReview task={task} requestKey={taskId} />);
    expect(screen.getByText(/规则审核：/)).toBeVisible();
    expect(screen.queryAllByRole("button", { name: "记录规则审核" })).toHaveLength(decision === "NEEDS_ADJUDICATION" ? 1 : 0);
  });
});
