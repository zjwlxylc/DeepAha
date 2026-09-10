import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import PreviewPage, { dynamic as previewDynamic } from "../app/review/investigations/[taskId]/unit-plans/[planId]/announcement-snapshot/page";
import RecordPage, { dynamic as recordDynamic } from "../app/review/investigations/[taskId]/announcement-snapshots/[snapshotId]/page";
import { loadAnnouncementPreviewAction, loadAnnouncementRecordAction, saveAnnouncementSnapshotAction } from "../app/review/investigations/announcement-snapshot-actions";
import { announcementRecordFixture, announcementSnapshotFixture } from "./announcement-snapshot-fixture";
import { unitSnapshotFixture } from "./investigations-fixture";
vi.mock("../app/review/investigations/announcement-snapshot-actions", () => ({ loadAnnouncementPreviewAction: vi.fn(), loadAnnouncementRecordAction: vi.fn(), saveAnnouncementSnapshotAction: vi.fn() }));
beforeEach(() => vi.resetAllMocks());

it("loads an uncached preview for the exact task and base without writing", async () => {
  const data = announcementSnapshotFixture(unitSnapshotFixture());
  vi.mocked(loadAnnouncementPreviewAction).mockResolvedValue({ ok: true, value: data });
  const taskId = data.task.task_id, planId = data.input.snapshot.base_v2.plan_id;
  render(await PreviewPage({ params: Promise.resolve({ taskId, planId }) }));
  expect(previewDynamic).toBe("force-dynamic");
  expect(loadAnnouncementPreviewAction).toHaveBeenCalledWith({ task_id: taskId, base_plan_id: planId });
  expect(screen.getByRole("heading", { name: "当前输入预览" })).toBeVisible();
  expect(saveAnnouncementSnapshotAction).not.toHaveBeenCalled();
});
it("trustfully reloads only the requested saved ID", async () => {
  const data = announcementSnapshotFixture(unitSnapshotFixture()); data.record = announcementRecordFixture(data.input);
  vi.mocked(loadAnnouncementRecordAction).mockResolvedValue({ ok: true, value: data });
  render(await RecordPage({ params: Promise.resolve({ taskId: data.task.task_id, snapshotId: data.record.snapshot_id }) }));
  expect(recordDynamic).toBe("force-dynamic");
  expect(loadAnnouncementRecordAction).toHaveBeenCalledWith(data.task.task_id, data.record.snapshot_id);
  expect(screen.getByRole("heading", { name: "已保存的范围记录" })).toBeVisible();
  expect(saveAnnouncementSnapshotAction).not.toHaveBeenCalled();
});
it("shows a safe error instead of saved contents when the trusted read fails", async () => {
  vi.mocked(loadAnnouncementRecordAction).mockResolvedValue({ ok: false, kind: "stale", error: "来源已更正，原记录不能再作为当前输入。" });
  render(await RecordPage({ params: Promise.resolve({ taskId: "task", snapshotId: "record" }) }));
  expect(screen.getByRole("alert")).toHaveTextContent("来源已更正");
  expect(screen.queryByRole("heading", { name: "完整基础条件快照" })).not.toBeInTheDocument();
});
