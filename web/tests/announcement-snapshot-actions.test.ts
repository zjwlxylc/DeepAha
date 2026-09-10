import { beforeEach, describe, expect, it, vi } from "vitest";
import { loadAnnouncementPreviewAction, loadAnnouncementRecordAction, saveAnnouncementSnapshotAction } from "../app/review/investigations/announcement-snapshot-actions";
import { announcementRecordFixture, announcementSnapshotFixture, announcementSnapshotId } from "./announcement-snapshot-fixture";
import { unitSnapshotFixture } from "./investigations-fixture";

vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "synthetic-reviewer-session" }) }) }));
const fixture = () => announcementSnapshotFixture(unitSnapshotFixture());
beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(globalThis, "fetch"); });
function responses(data = fixture()) {
  const record = announcementRecordFixture(data.input);
  vi.mocked(fetch).mockImplementation(async (url, init) => Response.json(init?.method === "POST" || String(url).includes(`/announcement-snapshots/${announcementSnapshotId}`) ? record : String(url).endsWith("announcement-snapshot-input") ? data.input : data.task));
  return { data, record, identity: { task_id: data.task.task_id, base_plan_id: data.input.snapshot.base_v2.plan_id } };
}
describe("private announcement snapshot actions", () => {
  it("previews without POST and reads current task/base privately", async () => {
    const { data, identity } = responses();
    expect(await loadAnnouncementPreviewAction(identity)).toEqual({ ok: true, value: data });
    expect(fetch).toHaveBeenCalledTimes(2);
    for (const [, init] of vi.mocked(fetch).mock.calls) { expect(init?.method).not.toBe("POST"); expect(init?.cache).toBe("no-store"); }
  });
  it("retries the original dependency hash after a lost receipt then rereads the saved record", async () => {
    const { identity, data } = responses();
    vi.mocked(fetch).mockRejectedValueOnce(new Error("private receipt failure"));
    expect(await saveAnnouncementSnapshotAction(identity, data.input.dependencies_hash)).toMatchObject({ ok: false, kind: "unavailable" });
    expect(await saveAnnouncementSnapshotAction(identity, data.input.dependencies_hash)).toMatchObject({ ok: true, value: { record: { snapshot_id: announcementSnapshotId } } });
    const posts = vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(2); expect(posts[1]).toEqual(posts[0]);
    expect(JSON.parse(posts[0][1]!.body as string)).toEqual({ expected_dependencies_hash: data.input.dependencies_hash });
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith(`/announcement-snapshots/${announcementSnapshotId}`))).toBe(true);
  });
  it.each(["task", "base", "base_hash", "condition", "scope", "target"])("rejects mismatched %s identity instead of displaying source data", async mismatch => {
    const data = fixture(), identity = { task_id: data.task.task_id, base_plan_id: data.input.snapshot.base_v2.plan_id };
    if (mismatch === "task") data.task.task_id = announcementSnapshotId;
    if (mismatch === "base") data.input.dependencies.base_plan_id = announcementSnapshotId;
    if (mismatch === "base_hash") data.input.dependencies.base_plan_hash = "0".repeat(64);
    if (mismatch === "condition") data.input.snapshot.announcement_conditions[0].condition = { ...data.input.snapshot.announcement_conditions[0].condition, source_index: 999 };
    if (mismatch === "scope") Object.assign(data.input.snapshot, { overall_qualification: "ELIGIBLE" });
    if (mismatch === "target") data.input.snapshot.announcement_conditions[0].applicability!.context.target = { ...data.input.snapshot.base_v2.plan.target, unit_version_id: announcementSnapshotId };
    responses(data);
    expect((await loadAnnouncementPreviewAction(identity)).ok).toBe(false);
  });
  it.each([403, 409, 503])("hides private details for %s", async status => {
    const { identity } = responses();
    vi.mocked(fetch).mockResolvedValue(Response.json({ detail: "private-error" }, { status }));
    const result = await loadAnnouncementPreviewAction(identity);
    expect(result.ok).toBe(false); expect(JSON.stringify(result)).not.toContain("private-error");
  });
  it("rejects a saved record id different from the requested id", async () => {
    const { data, record } = responses();
    record.snapshot_id = data.task.task_id;
    expect((await loadAnnouncementRecordAction(data.task.task_id, announcementSnapshotId)).ok).toBe(false);
  });
  it("rejects a successful POST receipt for a different dependency hash", async () => {
    const { identity, data, record } = responses();
    record.dependencies_hash = "0".repeat(64);
    expect((await saveAnnouncementSnapshotAction(identity, data.input.dependencies_hash)).ok).toBe(false);
  });
});
