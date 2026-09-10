import { ruleReadyTask } from "./investigations-fixture";
import { beforeEach, expect, it, vi } from "vitest";
import { loadGroupPreviewAction, loadGroupRecordAction, saveGroupSourceAction } from "../app/review/investigations/group-source-actions";
import { groupSourceFixture, groupRecordFixture, groupRecordId } from "./group-source-fixture";
vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "synthetic-reviewer-session" }) }) }));
beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(globalThis, "fetch"); });
function responses(data = groupSourceFixture(ruleReadyTask())) {
  const record = groupRecordFixture(data), identity = { task_id: data.task.task_id, entity_id: data.preview.source.source_group.id };
  vi.mocked(fetch).mockImplementation(async (url, init) => Response.json(init?.method === "POST" || String(url).includes(`/group-bindings/`) ? record : String(url).includes("group-source-input?") ? data.preview : data.task));
  return { data, record, identity };
}
it("previews all members privately without writing", async () => {
  const { data, identity } = responses();
  expect(await loadGroupPreviewAction(identity)).toEqual({ ok: true, value: data });
  expect(fetch).toHaveBeenCalledTimes(2);
  for (const [, init] of vi.mocked(fetch).mock.calls) { expect(init?.method).not.toBe("POST"); expect(init?.cache).toBe("no-store"); }
});
it("retries only the original source hash and rereads the exact saved record", async () => {
  const { data, identity } = responses(); vi.mocked(fetch).mockRejectedValueOnce(new Error("private failed receipt"));
  expect(await saveGroupSourceAction(identity, data.preview.source_hash)).toMatchObject({ ok: false, kind: "unavailable" });
  expect(await saveGroupSourceAction(identity, data.preview.source_hash)).toMatchObject({ ok: true, value: { preview: { registration: { group_binding_id: groupRecordId } } } });
  const posts = vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts).toHaveLength(2); expect(posts[1]).toEqual(posts[0]);
  expect(JSON.parse(posts[0][1]!.body as string)).toEqual({ entity_id: identity.entity_id, expected_source_hash: data.preview.source_hash });
});
it.each(["task", "binding", "group", "subset", "order", "state", "position", "membership", "scope", "bundle"])("rejects mismatched %s instead of showing partial or unrelated source", async kind => {
  const { data, identity } = responses(), s = data.preview.source;
  if (kind === "task") data.task.task_id = groupRecordId;
  if (kind === "binding") s.binding_id = groupRecordId;
  if (kind === "group") s.source_entity.id = "another-group";
  if (kind === "subset") s.members.pop();
  if (kind === "order") s.members.reverse();
  if (kind === "state") s.members[1].state = "BOUND";
  if (kind === "position") s.members[0].position_binding = { ...s.members[0].position_binding!, opportunity_unit_id: groupRecordId };
  if (kind === "membership") s.membership_status = "ALL_MEMBERS_BOUND";
  if (kind === "scope") Object.assign(s, { scope: "VERIFIED_FACTS" });
  if (kind === "bundle") data.task.entity_binding!.bundle_status = "SUPERSEDED";
  expect((await loadGroupPreviewAction(identity)).ok).toBe(false);
});
it.each([401, 403, 404, 409, 503])("sanitizes %s without exposing private details", async status => {
  const { identity } = responses(); vi.mocked(fetch).mockResolvedValue(Response.json({ detail: "private-secret" }, { status }));
  const result = await loadGroupPreviewAction(identity); expect(result.ok).toBe(false); expect(JSON.stringify(result)).not.toContain("private-secret");
});
it("rejects a returned record with the wrong ID", async () => {
  const { data, record } = responses(); record.group_binding_id = data.task.task_id;
  expect((await loadGroupRecordAction(data.task.task_id, groupRecordId)).ok).toBe(false);
});
it("rejects a receipt for another source hash", async () => {
  const { data, identity, record } = responses(); record.source_hash = "f".repeat(64);
  expect((await saveGroupSourceAction(identity, data.preview.source_hash)).ok).toBe(false);
});
it("rejects a preview registration that belongs to another group identity", async () => {
  const { data, record, identity } = responses(); data.preview.registration = record; data.preview.existing_group_id = groupRecordId;
  expect((await loadGroupPreviewAction(identity)).ok).toBe(false);
});
