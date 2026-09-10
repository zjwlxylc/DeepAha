import { beforeEach, expect, it, vi } from "vitest";
import { loadGroupRuleReviewAction, submitGroupRuleReviewAction } from "../app/review/investigations/group-rule-review-actions";
import { groupFactFixture, fixtureHash } from "./group-fact-fixture";
import { groupRuleFixture } from "./group-rule-fixture";
import { groupSourceFixture, groupRecordFixture } from "./group-source-fixture";
import { ruleReadyTask } from "./investigations-fixture";
import { groupRuleReviewFixture } from "./group-rule-review-fixture";
vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "synthetic" }) }) }));
beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(globalThis, "fetch"); });
function setup() {
  const source = groupSourceFixture(ruleReadyTask()), data = groupFactFixture(source, groupRecordFixture(source));
  const preview = groupRuleFixture(data), record = groupRuleReviewFixture(preview);
  vi.mocked(fetch).mockImplementation(async url => Response.json(String(url).endsWith("/rules/preview") ? preview : String(url).includes("/group-rules/") || String(url).endsWith("/rules") ? record : String(url).includes("/group-facts/") ? data.record : String(url).includes("/group-bindings/") ? data.source.preview.registration : data.source.task));
  return { data, preview, record, task: data.source.task.task_id, load: () => loadGroupRuleReviewAction(data.source.task.task_id, record.preparation_id) };
}
it("reads matching exact current preview without mutation", async () => {
  const { load, record } = setup(); expect(await load()).toEqual({ ok: true, value: record });
  expect(vi.mocked(fetch).mock.calls.every(([, init]) => init?.method !== "POST")).toBe(true);
});
it.each(["hash", "preview", "row", "candidate", "unknown", "factset", "history"])("rejects rehashed inconsistent %s", async kind => {
  const { record, load } = setup();
  if (kind === "hash") record.result_hash = "f".repeat(64);
  if (kind === "preview") record.result.preview.result_hash = "f".repeat(64);
  if (kind === "row") record.result.rows.pop();
  if (kind === "candidate") record.result.rows[0].rule_candidate_id = null;
  if (kind === "unknown") record.result.rows[1].rule_candidate_id = record.result.rows[0].rule_candidate_id;
  if (kind === "factset") record.fact_set_id = record.preparation_id;
  if (kind === "history") record.decisions.bad = {} as never;
  if (kind !== "hash") record.result_hash = fixtureHash(record.result);
  expect(await load()).toMatchObject({ ok: false, kind: "stale" });
});
it("saves using a stable key and rereads the saved record", async () => {
  const { task, preview, record } = setup();
  const command = { kind: "prepare" as const, fact_preparation_id: preview.result.fact_review.preparation_id, expected_preview_hash: preview.result_hash };
  expect(await submitGroupRuleReviewAction(task, command)).toEqual({ ok: true, value: record });
  await submitGroupRuleReviewAction(task, command);
  const posts = vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts).toHaveLength(2); expect(posts[0][1]?.headers).toEqual(posts[1][1]?.headers);
});
it.each([401, 403, 404, 409, 503])("hides stale payload on %s", async status => {
  const { load } = setup(); vi.mocked(fetch).mockResolvedValue(Response.json({ secret: true }, { status }));
  const result = await load(); expect(result.ok).toBe(false); expect(JSON.stringify(result)).not.toContain("secret");
});
it("rejects invalid identifiers without requesting", async () => { setup(); expect((await loadGroupRuleReviewAction("bad", "bad")).ok).toBe(false); expect(fetch).not.toHaveBeenCalled(); });
it.each([false, true])("checks the submitted assessment, allowing only timestamp representation differences (tamper=%s)", async tamper => {
  const { task, record } = setup(), candidate = record.result.rows[0];
  const evidence = candidate.evidence_ref_ids.map(id => ({ evidence_ref_id: id, authority: "FORMAL_OFFICIAL_ATTACHMENT" as const, relation: "SUPPORTS" as const, effective_at: "2026-09-01T00:00:00.000Z", applicability: "APPLIES_TO_EXACT_TARGET" as const, reason: "明确适用当前组" }));
  const d = { decision_id: "019d0000-0000-7000-8000-000000009099", rule_candidate_id: candidate.rule_candidate_id!, decision: "APPROVE" as const, reason: "完整审核", evidence: evidence.map(e => ({ ...e, effective_at: "2026-09-01T00:00:00Z", reason: tamper ? "另一个说明" : e.reason })), reviewer_id: record.reviewer_id, created_at: record.created_at };
  record.decisions[d.rule_candidate_id] = d; record.history = [d];
  const result = await submitGroupRuleReviewAction(task, { kind: "decision", preparation_id: record.preparation_id, expected_preparation_hash: record.result_hash, rule_candidate_id: candidate.rule_candidate_id!, decision: "APPROVE", reason: "完整审核", evidence });
  expect(result.ok).toBe(!tamper);
});
