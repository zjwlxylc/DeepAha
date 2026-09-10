import { beforeEach, expect, it, vi } from "vitest";
import { loadGroupFactRecordAction, submitGroupFactAction } from "../app/review/investigations/group-fact-actions";
import { groupFactFixture, fixtureHash } from "./group-fact-fixture";
import { groupSourceFixture, groupRecordFixture } from "./group-source-fixture";
import { ruleReadyTask } from "./investigations-fixture";
vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "synthetic" }) }) }));
beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(globalThis, "fetch"); });
function setup() {
  const source = groupSourceFixture(ruleReadyTask()), data = groupFactFixture(source, groupRecordFixture(source));
  vi.mocked(fetch).mockImplementation(async url => Response.json(String(url).includes("/group-facts/") || String(url).endsWith("/facts") ? data.record : String(url).includes("/group-bindings/") ? data.source.preview.registration : data.source.task));
  return data;
}
it("reads exact group facts, full denominator and evidence without a write", async () => {
  const data = setup(); expect(await loadGroupFactRecordAction(data.source.task.task_id, data.record!.preparation_id)).toEqual({ ok: true, value: data });
  expect(fetch).toHaveBeenCalledTimes(3); for (const [, init] of vi.mocked(fetch).mock.calls) { expect(init?.cache).toBe("no-store"); expect(init?.method).not.toBe("POST"); }
});
it.each(["hash", "original", "rows", "excluded", "reference", "candidate", "group", "check", "decision"])("rejects forged %s even with recomputed receipt hash", async kind => {
  const data = setup(), record = data.record!, row = record.result.rows[0];
  if (kind === "hash") record.result_hash = "f".repeat(64);
  if (kind === "original") row.original = { ...row.original, value: "博士" };
  if (kind === "rows") record.result.rows.pop();
  if (kind === "excluded") record.result.excluded_rows = [];
  if (kind === "reference") row.evidence[0].reference = { ...row.evidence[0].reference, quote: "博士" };
  if (kind === "candidate") row.candidate_id = "not-an-id";
  if (kind === "group") record.result.group_source = { ...record.result.group_source, group_identity: { ...record.result.group_source.group_identity, unit_kind: "POSITION" as "GROUP" } };
  if (kind === "check") record.result.check_hash = "f".repeat(64);
  if (kind === "decision") record.decisions.foreign = { candidate_id: "foreign", decision_id: record.preparation_id, decision: "APPROVE", reason: "Synthetic", reviewer_id: record.reviewer_id, created_at: record.created_at };
  if (kind !== "hash") record.result_hash = fixtureHash(record.result);
  expect((await loadGroupFactRecordAction(data.source.task.task_id, record.preparation_id)).ok).toBe(false);
});
it("retries the same preparation request and reads the saved URL", async () => {
  const data = setup(), source = data.source.preview.registration!;
  const command = { kind: "prepare" as const, group_binding_id: source.group_binding_id, check_id: data.record!.result.check_id, expected_source_hash: source.source_hash };
  vi.mocked(fetch).mockRejectedValueOnce(new Error("secret"));
  expect(await submitGroupFactAction(data.source.task.task_id, command)).toMatchObject({ ok: false, kind: "unavailable" });
  expect(await submitGroupFactAction(data.source.task.task_id, command)).toMatchObject({ ok: true });
  const posts = vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts).toHaveLength(2); expect(posts[0]).toEqual(posts[1]); expect(JSON.parse(posts[0][1]!.body as string)).toEqual({ check_id: command.check_id, expected_source_hash: command.expected_source_hash });
});
it.each([401, 403, 404, 409, 503])("sanitizes %s and hides the receipt", async status => {
  const data = setup(); vi.mocked(fetch).mockResolvedValue(Response.json({ detail: "secret" }, { status }));
  const result = await loadGroupFactRecordAction(data.source.task.task_id, data.record!.preparation_id); expect(result.ok).toBe(false); expect(JSON.stringify(result)).not.toContain("secret");
});
it("rejects malformed decisions before posting", async () => {
  const data = setup(); expect((await submitGroupFactAction(data.source.task.task_id, { kind: "decision", preparation_id: data.record!.preparation_id, expected_preparation_hash: data.record!.result_hash, candidate_id: data.record!.result.rows[0].candidate_id!, reason: "  ", decision: "APPROVE", evidence_support: "SUPPORTED", precedence_check: "PASSED" })).ok).toBe(false); expect(fetch).not.toHaveBeenCalled();
});
it.each([null, "从原始材料恢复的备注"])("accepts only the known legacy display-note addition (%s)", async note => {
  const data = setup(), record = data.record!;
  record.result.rows[0].original = { ...record.result.rows[0].original }; delete record.result.rows[0].original.note;
  data.source.task.facts[0] = { ...data.source.task.facts[0], note };
  const frozenPeer = { ...data.source.task.facts[3] }; delete frozenPeer.note;
  record.result.excluded_rows[0].source_hash = fixtureHash(frozenPeer); data.source.task.facts[3] = { ...data.source.task.facts[3], note };
  record.result_hash = fixtureHash(record.result);
  expect(await loadGroupFactRecordAction(data.source.task.task_id, record.preparation_id)).toMatchObject({ ok: true });
});
it("still rejects a changed note that was present in the frozen fact", async () => {
  const data = setup(); data.source.task.facts[0] = { ...data.source.task.facts[0], note: "改写已有备注" };
  expect((await loadGroupFactRecordAction(data.source.task.task_id, data.record!.preparation_id)).ok).toBe(false);
});
it.each(["decision", "promote"] as const)("does not report %s saved when reread has no matching receipt", async kind => {
  const data = setup(), record = data.record!;
  const base = { preparation_id: record.preparation_id, expected_preparation_hash: record.result_hash, reason: "Synthetic new decision" };
  const command = kind === "decision" ? { ...base, kind, candidate_id: record.result.rows[0].candidate_id!, decision: "APPROVE" as const, evidence_support: "SUPPORTED" as const, precedence_check: "PASSED" as const } : { ...base, kind };
  expect(await submitGroupFactAction(data.source.task.task_id, command)).toMatchObject({ ok: false, kind: "stale" });
});
