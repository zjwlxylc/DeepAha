import { expect, it, vi } from "vitest";
import { loadRelationIndex, loadRelation, decideRelation } from "../app/review/investigations/relation-actions";
import { postInvestigation } from "../lib/investigations";
import fixture from "./relation-review-fixture.json";
import { humanTestFetch } from "../lib/local-human-test";
vi.mock("../lib/local-human-test", () => ({ humanTestFetch: vi.fn() }));
vi.mock("../lib/investigations", () => ({ postInvestigation: vi.fn() }));
const task = "01900000-0000-7000-8000-000000000001", plan = "01900000-0000-7000-8000-000000000002";
it("keeps the plan index bound to the requested task and plan", async () => {
  vi.mocked(humanTestFetch).mockResolvedValue({ task_id: task, target_plan_id: plan, proposals: [] });
  expect((await loadRelationIndex(task, plan)).ok).toBe(true);
  vi.mocked(humanTestFetch).mockResolvedValue({ task_id: plan, target_plan_id: task, proposals: [] });
  expect((await loadRelationIndex(task, plan)).ok).toBe(false);
});
it("accepts real saved and approved API exports without rehashing frozen JSON", async () => {
  for (const value of [fixture.saved, fixture.approved, fixture.rejected]) {
    vi.mocked(humanTestFetch).mockResolvedValue(value);
    expect(await loadRelation(fixture.task, fixture.plan, fixture.saved.proposal_id)).toEqual({ ok: true, value });
  }
});
it("binds a decision receipt to the submitted request and stable proposal hash", async () => {
  vi.mocked(humanTestFetch).mockResolvedValue(fixture.saved);
  const d = fixture.approved.decision;
  const request = { proposal_id: fixture.saved.proposal_id, expected_proposal_payload_hash: fixture.saved.proposal_payload_sha256, previous_decision_id: null, decision: "APPROVE" as const, reason: d.reason };
  vi.mocked(postInvestigation).mockResolvedValue(fixture.approved);
  expect((await decideRelation(fixture.task, fixture.plan, request, task)).ok).toBe(true);
  expect((await decideRelation(fixture.task, fixture.plan, { ...request, reason: "wrong reason" }, task)).ok).toBe(false);
});
it("rejects the wrong plan before any decision POST", async () => {
  vi.mocked(postInvestigation).mockClear();
  vi.mocked(humanTestFetch).mockResolvedValue(fixture.saved);
  const request = { proposal_id: fixture.saved.proposal_id, expected_proposal_payload_hash: fixture.saved.proposal_payload_sha256, previous_decision_id: null, decision: "APPROVE" as const, reason: "核对关系" };
  expect((await decideRelation(fixture.task, plan, request, task)).ok).toBe(false);
  expect(postInvestigation).not.toHaveBeenCalled();
});
