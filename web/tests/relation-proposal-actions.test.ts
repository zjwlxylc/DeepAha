import { beforeEach, expect, it, vi } from "vitest";
import { loadProposalContext, proposeRelation } from "../app/review/investigations/proposal-actions";
import { humanTestFetch } from "../lib/local-human-test";
import { postInvestigation } from "../lib/investigations";
import f from "./relation-review-fixture.json";
vi.mock("../lib/local-human-test", () => ({ humanTestFetch: vi.fn() }));
vi.mock("../lib/investigations", () => ({ postInvestigation: vi.fn() }));
const p = f.saved.package.proposal;
const context = { task_id: f.task, target_plan_id: f.plan, review: p.source_review, review_hash: p.source_review_hash, evidence_options: [], next_cursor: null };
const request = { target_plan_id: f.plan, expected_review_hash: p.source_review_hash, condition_ids: p.condition_ids, relation: p.relation, displaced_condition_ids: p.displaced_condition_ids, reason: p.reason,
  evidence: p.evidence.map(({ member_id, block_id, quote, purpose, condition_ids }) => ({ member_id, block_id, quote, purpose, condition_ids })) };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(humanTestFetch).mockResolvedValue(context); vi.mocked(postInvestigation).mockResolvedValue(f.saved); });
it("loads authenticated context without recomputing frozen numeric hashes", async () => {
  expect((await loadProposalContext(f.task, f.plan)).ok).toBe(true);
  vi.mocked(humanTestFetch).mockResolvedValue({ ...context, target_plan_id: f.task });
  expect((await loadProposalContext(f.task, f.plan)).ok).toBe(false);
});
it("sends a thin request, preserves literal quotes and stable retry key", async () => {
  const input = { ...request, producer_id: f.task, source_review: {} };
  expect((await proposeRelation(f.task, f.plan, input, f.task)).ok).toBe(true);
  await proposeRelation(f.task, f.plan, input, f.task);
  const calls = vi.mocked(postInvestigation).mock.calls;
  expect(calls[0]).toEqual(calls[1]);
  expect(calls[0][1]).toEqual(request);
});
it("rejects stale source and wrong plan before POST", async () => {
  expect((await proposeRelation(f.task, f.plan, { ...request, expected_review_hash: "0".repeat(64) }, f.task)).ok).toBe(false);
  expect((await proposeRelation(f.task, f.task, request, f.task)).ok).toBe(false);
  expect(postInvestigation).not.toHaveBeenCalled();
});
it("does not navigate on a mismatched receipt", async () => {
  expect((await proposeRelation(f.task, f.plan, { ...request, reason: "another reason" }, f.task)).ok).toBe(false);
});
