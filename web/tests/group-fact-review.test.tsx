import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import GroupFactReview from "../components/investigations/group-fact-review";
import { loadGroupFactRecordAction, submitGroupFactAction } from "../app/review/investigations/group-fact-actions";
import { groupFactFixture } from "./group-fact-fixture";
import { groupSourceFixture, groupRecordFixture } from "./group-source-fixture";
import { ruleReadyTask } from "./investigations-fixture";
vi.mock("../app/review/investigations/group-fact-actions", () => ({ loadGroupFactRecordAction: vi.fn(), loadGroupFactStartAction: vi.fn(), submitGroupFactAction: vi.fn() }));
beforeEach(() => vi.resetAllMocks());
function setup() { const source = groupSourceFixture(ruleReadyTask()); return groupFactFixture(source, groupRecordFixture(source)); }
it("keeps original fields, unknown restrictions and unverified fields visible", () => {
  const data = setup(); render(<GroupFactReview taskId={data.source.task.task_id} initialResult={{ ok: true, value: data }} />);
  expect(screen.getByText(/组字段 3 项；可审核 2 项；待处理 1 项/)).toBeVisible();
  const unknown = within(screen.getByRole("article", { name: "组字段：户籍条件" }));
  expect(unknown.queryByRole("option", { name: "批准字段" })).not.toBeInTheDocument(); expect(unknown.getByRole("option", { name: "保留未知" })).toBeInTheDocument();
  expect(within(screen.getByRole("article", { name: "组字段：Word 补充条件" })).queryByRole("button")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "保存组事实集" })).not.toBeInTheDocument();
});
it("does not prepare automatically and exposes a fixed record link after explicit preparation", async () => {
  const data = setup(); vi.mocked(submitGroupFactAction).mockResolvedValue({ ok: true, value: data });
  render(<GroupFactReview taskId={data.source.task.task_id} groupId={data.source.preview.registration!.group_binding_id} initialResult={{ ok: true, value: { ...data, record: null } }} />);
  expect(submitGroupFactAction).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole("button", { name: "准备组字段候选" }));
  expect(await screen.findByRole("link", { name: "打开已保存审核记录" })).toHaveAttribute("href", `/review/investigations/${data.source.task.task_id}/group-facts/${data.record!.preparation_id}`);
});
it.each(["stale", "forbidden", "unavailable"] as const)("hides saved rows after %s read failure", async kind => {
  const data = setup(); vi.mocked(loadGroupFactRecordAction).mockResolvedValue({ ok: false, kind, error: "当前记录不可用" });
  render(<GroupFactReview taskId={data.source.task.task_id} prepId={data.record!.preparation_id} initialResult={{ ok: true, value: data }} />);
  fireEvent.click(screen.getByRole("button", { name: "重新读取当前审核记录" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("当前记录不可用"); expect(screen.queryByRole("article")).not.toBeInTheDocument();
});
it("retries the frozen command after lost receipt, without retaining editable old rows", async () => {
  const data = setup(); vi.mocked(submitGroupFactAction).mockResolvedValueOnce({ ok: false, kind: "unavailable", error: "丢失回执" }).mockResolvedValue({ ok: true, value: data });
  render(<GroupFactReview taskId={data.source.task.task_id} initialResult={{ ok: true, value: data }} />);
  const field = within(screen.getByRole("article", { name: "组字段：学历要求" }));
  fireEvent.change(field.getByLabelText("字段决定"), { target: { value: "APPROVE" } });
  fireEvent.change(field.getByLabelText("原文是否支持候选"), { target: { value: "SUPPORTED" } });
  fireEvent.change(field.getByLabelText("更正与条件优先级"), { target: { value: "PASSED" } });
  fireEvent.change(field.getByLabelText("审核依据"), { target: { value: "已核对原件（合成）" } });
  fireEvent.submit(field.getByRole("button", { name: "记录字段审核" }).closest("form")!);
  fireEvent.click(await screen.findByRole("button", { name: "重试原审核请求" }));
  await waitFor(() => expect(submitGroupFactAction).toHaveBeenCalledTimes(2)); expect(vi.mocked(submitGroupFactAction).mock.calls[0]).toEqual(vi.mocked(submitGroupFactAction).mock.calls[1]);
});
it("saves only after both processable fields have final decisions and retains unresolved fields", async () => {
  const data = setup(), record = data.record!;
  for (const [index, row] of record.result.rows.slice(0, 2).entries()) record.decisions[row.candidate_id!] = { candidate_id: row.candidate_id!, decision_id: record.preparation_id, decision: index ? "UNKNOWN" : "APPROVE", reason: "合成", reviewer_id: record.reviewer_id, created_at: record.created_at };
  vi.mocked(submitGroupFactAction).mockResolvedValue({ ok: true, value: { ...data, record: { ...record, fact_set: { fact_set_id: record.preparation_id, status: "ACTIVE", version: 1, reason: "合成保存" } } } });
  render(<GroupFactReview taskId={data.source.task.task_id} initialResult={{ ok: true, value: data }} />);
  fireEvent.change(screen.getByLabelText("保存依据"), { target: { value: "合成保存" } }); fireEvent.submit(screen.getByRole("button", { name: "保存组事实集" }).closest("form")!);
  expect(await screen.findByText(/已保存组事实集/)).toBeVisible(); expect(screen.getByRole("article", { name: "组字段：Word 补充条件" })).toBeVisible();
});
