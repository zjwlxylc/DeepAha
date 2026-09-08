import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import UnitPlanView from "../components/investigations/unit-plan-view";
import { applicabilityIds, applicabilityTaskFixture } from "./rule-applicability-fixture";
import { unitSnapshotFixture } from "./investigations-fixture";

describe("announcement applicability entry", () => {
  it("links the current approved announcement rule to this exact target plan", () => {
    const { task, snapshot } = applicabilityTaskFixture(unitSnapshotFixture());
    render(<UnitPlanView task={task} snapshot={snapshot} />);
    expect(screen.getByRole("link", { name: /审阅公告规则适用性/ })).toHaveAttribute("href",
      `/review/investigations/${task.task_id}/unit-plans/${snapshot.plan_id}/applicability/${applicabilityIds.sourcePreparation}/${applicabilityIds.sourceCandidate}`);
  });
  it.each(["pending", "rejected", "binding", "check", "fact_set", "version", "employer"])("excludes %s source rules", changed => {
    const { task, snapshot } = applicabilityTaskFixture(unitSnapshotFixture());
    const source = task.rule_review!.current[1];
    if (changed === "pending" || changed === "rejected") source.decisions[applicabilityIds.sourceCandidate].decision = changed === "pending" ? "NEEDS_ADJUDICATION" : "REJECT";
    if (changed === "binding") source.binding_id = applicabilityIds.member;
    if (changed === "check") source.check_id = applicabilityIds.member;
    if (changed === "fact_set") task.fact_review!.current!.active_fact_sets.announcement.fact_set_id = applicabilityIds.member;
    if (changed === "version") source.target.opportunity_version += 1;
    if (changed === "employer") source.target.entity_kind = "employer";
    render(<UnitPlanView task={task} snapshot={snapshot} />);
    expect(screen.queryByRole("link", { name: /审阅公告规则适用性/ })).not.toBeInTheDocument();
  });
});
