import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AnnouncementSnapshotReview from "../components/investigations/announcement-snapshot-review";
import UnitPlanView from "../components/investigations/unit-plan-view";
import { loadAnnouncementPreviewAction, loadAnnouncementRecordAction, saveAnnouncementSnapshotAction } from "../app/review/investigations/announcement-snapshot-actions";
import { announcementRecordFixture, announcementSnapshotFixture } from "./announcement-snapshot-fixture";
import { unitSnapshotFixture } from "./investigations-fixture";
import type { AnnouncementSnapshotResult } from "../lib/announcement-snapshots";
vi.mock("../app/review/investigations/announcement-snapshot-actions", () => ({ loadAnnouncementPreviewAction: vi.fn(), loadAnnouncementRecordAction: vi.fn(), saveAnnouncementSnapshotAction: vi.fn() }));
const fixture = () => announcementSnapshotFixture(unitSnapshotFixture());
beforeEach(() => { vi.resetAllMocks(); });
function mount(data = fixture()) { render(<AnnouncementSnapshotReview taskId={data.task.task_id} basePlanId={data.input.snapshot.base_v2.plan_id} initialResult={{ ok: true, value: data }} />); return data; }
describe("announcement scope snapshot UI", () => {
  it("previews three distinct dispositions, keeps the full base and never automatically saves", () => {
    mount();
    expect(screen.getByRole("heading", { name: "继承的公告条件 · 1" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "明确排除的公告条件 · 1" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "仍待处理的公告条件 · 1" })).toBeVisible();
    expect(screen.getByText("公告证据尚未完成核验")).toBeVisible();
    expect(screen.getByText(/尚不能用于个人资格判断/)).toBeVisible();
    expect(screen.getByRole("heading", { name: "完整基础条件快照" })).toBeVisible();
    expect(screen.getByText(/全调查共 8 个源字段/)).toBeVisible();
    expect(within(screen.getByRole("region", { name: "仍待处理的公告条件 · 1" })).getByText(/Word 补充说明尚未核验/)).toBeVisible();
    expect(within(screen.getByRole("region", { name: "完整基础条件快照" })).getByText(/Word 补充说明尚未核验/)).toBeVisible();
    expect(screen.queryByRole("link", { name: "查看公告继承快照" })).not.toBeInTheDocument();
    expect(saveAnnouncementSnapshotAction).not.toHaveBeenCalled();
  });
  it("hides previous source data after a lost receipt and retries only its original hash", async () => {
    const data = mount(), saved = { ...data, record: announcementRecordFixture(data.input) };
    vi.mocked(saveAnnouncementSnapshotAction).mockResolvedValueOnce({ ok: false, kind: "unavailable", error: "回执丢失" }).mockResolvedValue({ ok: true, value: saved });
    fireEvent.click(screen.getByRole("button", { name: "保存当前派生快照" }));
    await screen.findByRole("button", { name: "重试保存原摘要" });
    expect(screen.queryByRole("heading", { name: "继承的公告条件 · 1" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试保存原摘要" }));
    await screen.findByRole("link", { name: "打开已保存快照" });
    const calls = vi.mocked(saveAnnouncementSnapshotAction).mock.calls;
    expect(calls).toHaveLength(2); expect(calls[1]).toEqual(calls[0]);
    expect(calls[0][1]).toBe(data.input.dependencies_hash);
    expect(screen.queryByRole("button", { name: "保存当前派生快照" })).not.toBeInTheDocument();
  });
  it.each(["forbidden", "stale"] as const)("hides stale content for %s and allows explicit fresh input", async kind => {
    const data = mount();
    vi.mocked(saveAnnouncementSnapshotAction).mockResolvedValue({ ok: false, kind, error: "当前输入不可用" });
    vi.mocked(loadAnnouncementPreviewAction).mockResolvedValue({ ok: true, value: { ...data, input: { ...data.input, dependencies_hash: "a".repeat(64) } } });
    fireEvent.click(screen.getByRole("button", { name: "保存当前派生快照" }));
    await screen.findByRole("alert");
    expect(screen.queryByText("公告学历条件")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重试保存原摘要" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新获取当前输入" }));
    await screen.findByRole("button", { name: "保存当前派生快照" });
    fireEvent.click(screen.getByRole("button", { name: "保存当前派生快照" }));
    await waitFor(() => expect(vi.mocked(saveAnnouncementSnapshotAction).mock.calls[1][1]).toBe("a".repeat(64)));
  });
  it("shows actual parent identity and exact applicability evidence links", () => {
    const data = mount();
    const inherited = screen.getByRole("region", { name: "继承的公告条件 · 1" });
    expect(within(inherited).getByText(/公告事实标识/)).toHaveTextContent(data.input.snapshot.announcement_conditions[0].source_fact!.verified_fact_id);
    expect(within(inherited).getByRole("link", { name: "查看适用性官方原文" })).toHaveAttribute("href", "https://example.test/announcement/0");
    expect(within(inherited).getByText("保留公告适用范围原文。").textContent).toBe("  保留公告适用范围原文。\n");
  });
  it("never renders an unsafe official source link", () => {
    const data = fixture(); data.input.snapshot.announcement_conditions[0].applicability!.evidence_snapshot[0].source_url = "javascript:alert(1)";
    mount(data);
    expect(within(screen.getByRole("region", { name: "继承的公告条件 · 1" })).queryByRole("link", { name: "查看适用性官方原文" })).not.toBeInTheDocument();
  });
  it("can recheck a saved record without submitting a new snapshot", async () => {
    const data = fixture(); data.record = announcementRecordFixture(data.input); mount(data);
    vi.mocked(loadAnnouncementRecordAction).mockResolvedValue({ ok: false, kind: "stale", error: "已更正，请读取当前输入" });
    fireEvent.click(screen.getByRole("button", { name: "重新核对已存快照" }));
    await screen.findByRole("alert");
    expect(loadAnnouncementRecordAction).toHaveBeenCalledWith(data.task.task_id, data.record.snapshot_id);
    expect(screen.queryByRole("heading", { name: "继承的公告条件 · 1" })).not.toBeInTheDocument();
    expect(saveAnnouncementSnapshotAction).not.toHaveBeenCalled();
  });
  it("renders a safe initial error and a retry control without old data", () => {
    const result: AnnouncementSnapshotResult = { ok: false, kind: "stale", error: "请返回当前基础快照" };
    render(<AnnouncementSnapshotReview taskId={fixture().task.task_id} snapshotId="saved-id" initialResult={result} />);
    expect(screen.getByRole("alert")).toHaveTextContent(result.error);
    expect(screen.queryByRole("button", { name: "保存当前派生快照" })).not.toBeInTheDocument();
  });
  it("links from the base snapshot to a read-only preview", () => {
    const data = unitSnapshotFixture(); render(<UnitPlanView task={data.task} snapshot={data.snapshot} />);
    expect(screen.getByRole("link", { name: "查看公告继承快照" })).toHaveAttribute("href", `/review/investigations/${data.task.task_id}/unit-plans/${data.snapshot.plan_id}/announcement-snapshot`);
  });
  it("keeps an empty announcement denominator explicit without inventing inherited conditions", () => {
    const data = fixture(); data.input.snapshot.announcement_conditions = [];
    data.input.snapshot.base_v2.plan.manifest.conditions = data.input.snapshot.base_v2.plan.manifest.conditions.filter(row => row.scope !== "ANNOUNCEMENT");
    mount(data);
    for (const name of ["继承的公告条件 · 0", "明确排除的公告条件 · 0", "仍待处理的公告条件 · 0"]) expect(screen.getByRole("heading", { name })).toBeVisible();
    expect(screen.getByText(/本页保留 0 条公告源条件/)).toBeVisible();
    expect(screen.getByRole("heading", { name: "完整基础条件快照" })).toBeVisible();
    expect(saveAnnouncementSnapshotAction).not.toHaveBeenCalled();
  });
});
