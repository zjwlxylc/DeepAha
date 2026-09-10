import { expect, it, vi } from "vitest";
import { loadRelationQueue } from "../app/review/investigations/queue-actions";
import { humanTestFetch } from "../lib/local-human-test";
import f from "./relation-queue-fixture.json";
vi.mock("../lib/local-human-test", () => ({ humanTestFetch: vi.fn() }));
it("accepts the real API queue and stale replay without rehashing raw sources", async () => {
  for (const v of [f.current, f.stale]) {
    vi.mocked(humanTestFetch).mockResolvedValue(v);
    expect(await loadRelationQueue(v.task_id, v.target_plan_id)).toEqual({ ok: true, value: v });
  }
});
it.each(["target", "status", "safety", "cursor", "duplicate", "ownership"])("rejects invalid queue %s", async attack => {
  const v = structuredClone(f.current);
  if (attack === "target") v.target_plan_id = v.task_id;
  if (attack === "status") v.proposals[0].status = "QUALIFIED";
  if (attack === "safety") v.executable = true;
  if (attack === "cursor") Object.assign(v, { next_after: v.proposals[0].proposal_id });
  if (attack === "duplicate") v.proposals.push(v.proposals[0]);
  if (attack === "ownership") Object.assign(v.proposals[0], { is_own_proposal: "true" });
  vi.mocked(humanTestFetch).mockResolvedValue(v);
  expect((await loadRelationQueue(f.current.task_id, f.current.target_plan_id)).ok).toBe(false);
});
