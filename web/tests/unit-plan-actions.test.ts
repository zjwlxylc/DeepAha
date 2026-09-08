import { beforeEach, describe, expect, it, vi } from "vitest";
import { prepareUnitPlanAction } from "../app/review/investigations/unit-plan-actions";
import { taskId, unitSnapshotFixture } from "./investigations-fixture";

vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "synthetic-reviewer-session" }) }) }));

const initial = { error: null, planId: null };
const { task, snapshot } = unitSnapshotFixture(), prep = task.rule_review!.current[0];
function form() {
  const data = new FormData();
  Object.entries({ task_id: taskId, request_key: taskId, delivery_hash: prep.delivery_hash,
    binding_id: prep.binding_id, check_id: prep.check_id, fact_preparation_id: prep.fact_preparation_id,
    fact_set_id: prep.fact_set_id, rule_preparation_id: prep.rule_preparation_id, entity_id: prep.entity_id,
  }).forEach(([key, value]) => data.set(key, value));
  return data;
}
beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(snapshot)); });
describe("snapshot action", () => {
  it("retries a lost response with the same exact source identities", async () => {
    const data = form(); vi.mocked(fetch).mockRejectedValueOnce(new Error("lost"));
    expect((await prepareUnitPlanAction(initial, data)).error).toContain("重试");
    expect(await prepareUnitPlanAction(initial, data)).toEqual({ error: null, planId: snapshot.plan_id });
    const [first, second] = vi.mocked(fetch).mock.calls;
    expect(second[1]!.body).toEqual(first[1]!.body); expect(second[1]!.headers).toEqual(first[1]!.headers);
    expect(JSON.parse(second[1]!.body as string)).toEqual({ delivery_hash: prep.delivery_hash, binding_id: prep.binding_id, check_id: prep.check_id,
      fact_preparation_id: prep.fact_preparation_id, fact_set_id: prep.fact_set_id, rule_preparation_id: prep.rule_preparation_id, entity_id: prep.entity_id });
  });
  it("rejects missing review identifiers before submitting", async () => {
    const data = form(); data.delete("check_id");
    expect((await prepareUnitPlanAction(initial, data)).error).toContain("核验回执"); expect(fetch).not.toHaveBeenCalled();
  });
  it.each([403, 409, 503])("never returns a snapshot link for HTTP %s", async status => {
    vi.mocked(fetch).mockResolvedValue(Response.json({ detail: {} }, { status }));
    const result = await prepareUnitPlanAction(initial, form());
    expect(result.planId).toBeNull(); expect(result.error).toBeTruthy();
    expect(fetch).toHaveBeenCalledOnce();
  });
});
