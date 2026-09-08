import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import InvestigationRuleReview from "../components/investigations/rule-review";
import UnitPlanView from "../components/investigations/unit-plan-view";
import { taskId, ruleReadyTask, unitSnapshotFixture } from "./investigations-fixture";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

describe("unit condition snapshot", () => {
  it("preserves unresolved conditions, source notes, evidence counts and peer exclusions", () => {
    const { task, snapshot } = unitSnapshotFixture();
    render(<UnitPlanView task={task} snapshot={snapshot} />);
    expect(screen.getByText(/全调查共 5 个源字段/)).toBeVisible();
    expect(screen.getByText(/通过 4 · 错误 0 · 未核验 1/)).toBeVisible();
    expect(screen.getByText(/调查后信息不足/)).toBeVisible();
    expect(screen.getByText(/证据尚不能定位核验/)).toBeVisible();
    expect(screen.getByText(/已拒绝，仍待处理/)).toBeVisible();
    expect(screen.getByText(/原始备注：示例疑点/)).toBeVisible();
    expect(screen.getByRole("heading", { name: "无关范围的源字段" })).toBeVisible();
    expect(screen.getByText(/整体资格保持不确定/)).toBeVisible();
    expect(screen.getAllByRole("link", { name: /下载原件/ })).toHaveLength(4);
  });
  it.each(["check", "binding", "facts", "rules", "active"])("does not display old conditions when %s changed", field => {
    const { task, snapshot } = unitSnapshotFixture();
    if (field === "check") task.evidence_check!.check_id = taskId;
    if (field === "binding") task.entity_binding!.binding_id = taskId;
    if (field === "facts") task.fact_review!.current!.result_hash = "x".repeat(64);
    if (field === "rules") task.rule_review!.current[0].result_hash = "x".repeat(64);
    if (field === "active") task.fact_review!.current!.active_fact_sets = {};
    render(<UnitPlanView task={task} snapshot={snapshot} />);
    expect(screen.getByRole("alert")).toHaveTextContent("快照关联版本已变化");
    expect(screen.queryByRole("heading", { name: "逐项条件与依据" })).not.toBeInTheDocument();
  });
  it("only shows the creation control after all rule candidates have terminal decisions", () => {
    const task = ruleReadyTask();
    const { rerender } = render(<InvestigationRuleReview task={task} requestKey={taskId} />);
    expect(screen.queryByRole("button", { name: "整理条件快照" })).not.toBeInTheDocument();
    rerender(<InvestigationRuleReview task={unitSnapshotFixture().task} requestKey={taskId} />);
    expect(screen.getByRole("button", { name: "整理条件快照" })).toBeVisible();
  });
});
