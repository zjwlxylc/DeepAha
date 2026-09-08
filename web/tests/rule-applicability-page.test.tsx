import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RuleApplicabilityPage from "../app/review/investigations/[taskId]/unit-plans/[planId]/applicability/[sourcePreparationId]/[candidateId]/page";
import { loadRuleApplicabilityAction } from "../app/review/investigations/rule-applicability-actions";
import { unitSnapshotFixture } from "./investigations-fixture";
import { applicabilityViewFixture } from "./rule-applicability-fixture";
vi.mock("../app/review/investigations/rule-applicability-actions", () => ({ loadRuleApplicabilityAction: vi.fn(), saveRuleApplicabilityAction: vi.fn() }));
const { identity, view } = applicabilityViewFixture(unitSnapshotFixture());
const params = Promise.resolve({ taskId: identity.task_id, planId: identity.target_plan_id, sourcePreparationId: identity.source_rule_preparation_id, candidateId: identity.source_rule_candidate_id });
beforeEach(() => { vi.resetAllMocks(); });
describe("private applicability page", () => {
  it("renders only the freshly loaded exact source and target", async () => {
    vi.mocked(loadRuleApplicabilityAction).mockResolvedValue({ ok: true, value: view });
    render(await RuleApplicabilityPage({ params }));
    expect(loadRuleApplicabilityAction).toHaveBeenCalledWith(identity);
    expect(screen.getByText("规则：学历 不低于 硕士")).toBeVisible();
  });
  it.each(["forbidden", "stale", "unavailable", "invalid"] as const)("shows a safe %s state without a decision form", async kind => {
    vi.mocked(loadRuleApplicabilityAction).mockResolvedValue({ ok: false, kind, error: "请从当前已授权的条件快照重新核对。" });
    render(await RuleApplicabilityPage({ params }));
    expect(screen.getByRole("alert")).toHaveTextContent("请从当前已授权的条件快照重新核对。");
    expect(screen.queryByLabelText("适用性决定")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "重新读取最新状态" })).toHaveAttribute("href", expect.stringContaining(identity.source_rule_candidate_id));
  });
});
