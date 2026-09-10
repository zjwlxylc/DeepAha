import { ruleReadyTask } from "./investigations-fixture";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import GroupSourceReview from "../components/investigations/group-source-review";
import GroupSourceLinks from "../components/investigations/group-source-links";
import { loadGroupPreviewAction, loadGroupRecordAction, saveGroupSourceAction } from "../app/review/investigations/group-source-actions";
import { groupSourceFixture, groupRecordFixture } from "./group-source-fixture";
vi.mock("../app/review/investigations/group-source-actions", () => ({ loadGroupPreviewAction: vi.fn(), loadGroupRecordAction: vi.fn(), saveGroupSourceAction: vi.fn() }));
beforeEach(() => vi.resetAllMocks());
function mount(data = groupSourceFixture(ruleReadyTask())) { render(<GroupSourceReview taskId={data.task.task_id} entityId={data.preview.source.source_group.id} initialResult={{ ok: true, value: data }} />); return data; }
it("shows complete ordered membership without promoting pending evidence or saving automatically", () => {
  mount(); expect(screen.getByRole("heading", { name: "完整组成员 · 2" })).toBeVisible();
  expect(screen.getByText("尚未关联的研究岗位")).toBeVisible();
  expect(screen.getByText("未处理 · UNPROCESSED")).toBeVisible();
  expect(screen.getByText(/不代表事实、规则或资格已批准/)).toBeVisible();
  expect(saveGroupSourceAction).not.toHaveBeenCalled();
});
it("hides old data after a lost receipt and retries the same source before linking to the saved ID", async () => {
  const data = mount(), saved = structuredClone(data); saved.preview.registration = groupRecordFixture(data);
  vi.mocked(saveGroupSourceAction).mockResolvedValueOnce({ ok: false, kind: "unavailable", error: "回执丢失" }).mockResolvedValue({ ok: true, value: saved });
  fireEvent.click(screen.getByRole("button", { name: "登记当前组来源" }));
  await screen.findByRole("button", { name: "重试登记原摘要" });
  expect(screen.queryByText("尚未关联的研究岗位")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "重试登记原摘要" }));
  await screen.findByRole("link", { name: "打开已登记来源" });
  const calls = vi.mocked(saveGroupSourceAction).mock.calls;
  expect(calls).toHaveLength(2); expect(calls[1]).toEqual(calls[0]);
  expect(screen.getByRole("link", { name: "打开已登记来源" })).toHaveAttribute("href", `/review/investigations/${data.task.task_id}/group-bindings/${saved.preview.registration.group_binding_id}`);
});
it.each(["stale", "forbidden"] as const)("hides source after %s and cannot retry the stale write", async kind => {
  const data = mount(); vi.mocked(saveGroupSourceAction).mockResolvedValue({ ok: false, kind, error: "来源不可用" });
  fireEvent.click(screen.getByRole("button", { name: "登记当前组来源" })); await screen.findByRole("alert");
  expect(screen.queryByRole("heading", { name: "完整组成员 · 2" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "重试登记原摘要" })).not.toBeInTheDocument();
  data.preview.source_hash = "e".repeat(64); vi.mocked(loadGroupPreviewAction).mockResolvedValue({ ok: true, value: data });
  fireEvent.click(screen.getByRole("button", { name: "重新获取当前输入" })); await screen.findByRole("button", { name: "登记当前组来源" });
  fireEvent.click(screen.getByRole("button", { name: "登记当前组来源" }));
  await waitFor(() => expect(vi.mocked(saveGroupSourceAction).mock.calls[1][1]).toBe(data.preview.source_hash));
});
it("rechecks the saved ID and hides a revoked record without POST", async () => {
  const data = groupSourceFixture(ruleReadyTask()); data.preview.registration = groupRecordFixture(data); mount(data);
  vi.mocked(loadGroupRecordAction).mockResolvedValue({ ok: false, kind: "forbidden", error: "权限已撤销" });
  fireEvent.click(screen.getByRole("button", { name: "重新核对已登记来源" })); await screen.findByRole("alert");
  expect(loadGroupRecordAction).toHaveBeenCalledWith(data.task.task_id, data.preview.registration.group_binding_id);
  expect(screen.queryByText(data.preview.registration.group_identity.public_id)).not.toBeInTheDocument();
  expect(saveGroupSourceAction).not.toHaveBeenCalled();
});
it("keeps an empty group explicit", () => {
  const data = groupSourceFixture(ruleReadyTask()); data.preview.source.members = []; data.preview.source.source_group.positions = []; data.preview.source.membership_status = "NO_MEMBERS";
  mount(data); expect(screen.getByText(/原组没有成员/)).toBeVisible();
  expect(screen.getByRole("heading", { name: "完整组成员 · 0" })).toBeVisible();
});
it("links only raw group identities from the approved frozen task", () => {
  const { task } = groupSourceFixture(ruleReadyTask()); render(<GroupSourceLinks task={task} />);
  expect(screen.getAllByRole("link")).toHaveLength(1);
  expect(screen.getByRole("link")).toHaveAttribute("href", `/review/investigations/${task.task_id}/group-source?entity_id=unit-1`);
});
it("does not offer group registration from stale bindings", () => {
  const { task } = groupSourceFixture(ruleReadyTask()); task.entity_binding!.bundle_status = "SUPERSEDED"; render(<GroupSourceLinks task={task} />);
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});
