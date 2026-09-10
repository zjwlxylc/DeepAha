import { beforeEach, expect, it, vi } from "vitest";
import { loadGroupRulePreviewAction } from "../app/review/investigations/group-rule-actions";
import { groupFactFixture, fixtureHash } from "./group-fact-fixture";
import { groupRuleFixture } from "./group-rule-fixture";
import { groupSourceFixture, groupRecordFixture } from "./group-source-fixture";
import { ruleReadyTask } from "./investigations-fixture";
vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "synthetic" }) }) }));
beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(globalThis, "fetch"); });
function setup() {
  const source = groupSourceFixture(ruleReadyTask()), data = groupFactFixture(source, groupRecordFixture(source));
  const preview = structuredClone(groupRuleFixture(data));
  vi.mocked(fetch).mockImplementation(async url => Response.json(String(url).endsWith("/rules/preview") ? preview : String(url).includes("/group-facts/") ? data.record : String(url).includes("/group-bindings/") ? data.source.preview.registration : data.source.task));
  return { data, preview, load: () => loadGroupRulePreviewAction(data.source.task.task_id, data.record!.preparation_id) };
}
it("reads exact current facts and a matching preview using GET only", async () => {
  const { preview, load } = setup(); expect(await load()).toEqual({ ok: true, value: preview });
  for (const [, init] of vi.mocked(fetch).mock.calls) { expect(init?.cache).toBe("no-store"); expect(init?.method).not.toBe("POST"); }
});
it.each(["hash", "group", "row", "candidate", "unknown", "evidence", "fact-set", "history", "scope", "deriver"])("rejects inconsistent %s even with recalculated hash", async kind => {
  const { preview, load } = setup(), result = preview.result;
  if (kind === "hash") preview.result_hash = "f".repeat(64);
  if (kind === "group") result.target = { ...result.target, unit_id: "019d0000-0000-7000-8000-000000009999" };
  if (kind === "row") result.rows.pop();
  if (kind === "candidate") result.rows[0].candidate_id = result.rows[1].candidate_id;
  if (kind === "unknown") result.rows[1].proposed_rule_payload = result.rows[0].proposed_rule_payload;
  if (kind === "evidence") result.rows[0].evidence_ref_ids = [];
  if (kind === "fact-set") result.fact_review.fact_set!.status = "STALE";
  if (kind === "history") result.fact_review.history = [];
  if (kind === "scope") result.scope = "APPROVED" as typeof result.scope;
  if (kind === "deriver") result.derivation_version = "future";
  if (kind !== "hash") preview.result_hash = fixtureHash(result);
  expect(await load()).toMatchObject({ ok: false, kind: "stale" });
});
it.each([401, 403, 404, 409, 503])("hides stale content and sanitizes %s", async status => {
  const { load } = setup(); vi.mocked(fetch).mockResolvedValue(Response.json({ detail: "secret" }, { status }));
  const result = await load(); expect(result.ok).toBe(false); expect(JSON.stringify(result)).not.toContain("secret");
});
it("rejects invalid identifiers without requesting", async () => { setup(); expect((await loadGroupRulePreviewAction("bad", "bad")).ok).toBe(false); expect(fetch).not.toHaveBeenCalled(); });
