import { ruleReadyTask } from "./investigations-fixture";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import PreviewPage, { dynamic as previewDynamic } from "../app/review/investigations/[taskId]/group-source/page";
import RecordPage, { dynamic as recordDynamic } from "../app/review/investigations/[taskId]/group-bindings/[recordId]/page";
import { loadGroupPreviewAction, loadGroupRecordAction, saveGroupSourceAction } from "../app/review/investigations/group-source-actions";
import { groupSourceFixture, groupRecordFixture } from "./group-source-fixture";
vi.mock("../app/review/investigations/group-source-actions", () => ({ loadGroupPreviewAction: vi.fn(), loadGroupRecordAction: vi.fn(), saveGroupSourceAction: vi.fn() }));
beforeEach(() => vi.resetAllMocks());
it("loads an uncached preview for the exact raw entity without saving", async () => {
  const data = groupSourceFixture(ruleReadyTask()); vi.mocked(loadGroupPreviewAction).mockResolvedValue({ ok: true, value: data });
  render(await PreviewPage({ params: Promise.resolve({ taskId: data.task.task_id }), searchParams: Promise.resolve({ entity_id: "unit-1" }) }));
  expect(previewDynamic).toBe("force-dynamic"); expect(loadGroupPreviewAction).toHaveBeenCalledWith({ task_id: data.task.task_id, entity_id: "unit-1" });
  expect(screen.getByRole("heading", { name: "当前组来源预览" })).toBeVisible(); expect(saveGroupSourceAction).not.toHaveBeenCalled();
});
it("rejects ambiguous entity query parameters", async () => {
  vi.mocked(loadGroupPreviewAction).mockResolvedValue({ ok: false, kind: "invalid", error: "标识不完整" });
  render(await PreviewPage({ params: Promise.resolve({ taskId: "task" }), searchParams: Promise.resolve({ entity_id: ["a", "b"] }) }));
  expect(loadGroupPreviewAction).toHaveBeenCalledWith({ task_id: "task", entity_id: "" }); expect(screen.getByRole("alert")).toBeVisible();
});
it("rereads the requested saved identity and never creates a new record", async () => {
  const data = groupSourceFixture(ruleReadyTask()); data.preview.registration = groupRecordFixture(data);
  vi.mocked(loadGroupRecordAction).mockResolvedValue({ ok: true, value: data });
  render(await RecordPage({ params: Promise.resolve({ taskId: data.task.task_id, recordId: data.preview.registration.group_binding_id }) }));
  expect(recordDynamic).toBe("force-dynamic"); expect(loadGroupRecordAction).toHaveBeenCalledWith(data.task.task_id, data.preview.registration.group_binding_id);
  expect(screen.getByRole("heading", { name: "已登记的组来源" })).toBeVisible(); expect(saveGroupSourceAction).not.toHaveBeenCalled();
});
it("does not retain saved contents when the fresh read fails", async () => {
  vi.mocked(loadGroupRecordAction).mockResolvedValue({ ok: false, kind: "stale", error: "来源已更正" });
  render(await RecordPage({ params: Promise.resolve({ taskId: "task", recordId: "record" }) }));
  expect(screen.getByRole("alert")).toHaveTextContent("来源已更正"); expect(screen.queryByRole("heading", { name: /完整组成员/ })).not.toBeInTheDocument();
});
