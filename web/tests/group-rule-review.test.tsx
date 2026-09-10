import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import GroupRuleReview from "../components/investigations/group-rule-review";
import { loadGroupRuleReviewAction, submitGroupRuleReviewAction } from "../app/review/investigations/group-rule-review-actions";
import { groupFactFixture } from "./group-fact-fixture";
import { groupRuleFixture } from "./group-rule-fixture";
import { groupRuleReviewFixture } from "./group-rule-review-fixture";
import { groupSourceFixture, groupRecordFixture } from "./group-source-fixture";
import { ruleReadyTask } from "./investigations-fixture";
import SavedPage, { dynamic } from "../app/review/investigations/[taskId]/group-rules/[prepId]/page";
const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("../app/review/investigations/group-rule-review-actions", () => ({ loadGroupRuleReviewAction: vi.fn(), submitGroupRuleReviewAction: vi.fn() }));
beforeEach(() => vi.clearAllMocks());
function fixture() { const source = groupSourceFixture(ruleReadyTask()); return groupRuleReviewFixture(groupRuleFixture(groupFactFixture(source, groupRecordFixture(source)))); }
function show() { const record = fixture(); render(<GroupRuleReview taskId="task" factId={record.fact_preparation_id} savedId={record.preparation_id} initial={{ kind: "review", result: { ok: true, value: record } }} />); return record; }
it("keeps full rows and starts without preapproved evidence", () => {
  show(); expect(screen.getAllByRole("article")).toHaveLength(3);
  expect(screen.getByLabelText("权威类别")).toHaveValue(""); expect(screen.getByLabelText("适用范围")).toHaveValue("UNRESOLVED");
  expect(screen.getByRole("button", { name: "提交独立审核" })).toBeDisabled();
  expect(screen.getByText("事实未知，不能形成资格规则")).toBeVisible();
  expect(screen.getByText("待处理：字段或证据尚不能用于规则")).toBeVisible();
});
it("does not enable approval until every assessment is explicit", () => {
  show(); fireEvent.change(screen.getByLabelText("审核决定"), { target: { value: "APPROVE" } }); fireEvent.change(screen.getByLabelText("审核说明"), { target: { value: "已复核" } });
  expect(screen.getByRole("button", { name: "提交独立审核" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("权威类别"), { target: { value: "FORMAL_OFFICIAL_ATTACHMENT" } });
  fireEvent.change(screen.getByLabelText("与规则的关系"), { target: { value: "SUPPORTS" } });
  fireEvent.change(screen.getByLabelText("官方材料生效时间（本地时区）"), { target: { value: "2026-09-01T08:00" } });
  fireEvent.change(screen.getByLabelText("适用范围"), { target: { value: "APPLIES_TO_EXACT_TARGET" } });
  fireEvent.change(screen.getByLabelText("证据评估说明"), { target: { value: "适用于此组" } });
  expect(screen.getByRole("button", { name: "提交独立审核" })).toBeEnabled();
});
it("saves and navigates to the exact returned record address", async () => {
  const record = fixture(); vi.mocked(submitGroupRuleReviewAction).mockResolvedValue({ ok: true, value: record });
  render(<GroupRuleReview taskId="task" factId={record.fact_preparation_id} initial={{ kind: "preview", result: { ok: true, value: record.result.preview } }} />);
  fireEvent.click(screen.getByRole("button", { name: "保存候选并进入审核" }));
  await waitFor(() => expect(replace).toHaveBeenCalledWith(`/review/investigations/task/group-rules/${record.preparation_id}`));
  expect(screen.queryAllByRole("article")).toHaveLength(0);
  expect(screen.queryByRole("button", { name: "提交独立审核" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "正在核对…" })).toBeDisabled();
});
it.each(["stale", "forbidden", "unavailable"] as const)("hides old forms on %s and restores only by explicit reload", async kind => {
  const record = show(); vi.mocked(loadGroupRuleReviewAction).mockResolvedValue({ ok: false, kind, error: "不可用" });
  fireEvent.click(screen.getByRole("button", { name: "重新读取当前审核" }));
  await waitFor(() => expect(screen.getByRole("alert")).toBeVisible()); expect(screen.queryByRole("article")).not.toBeInTheDocument();
  vi.mocked(loadGroupRuleReviewAction).mockResolvedValue({ ok: true, value: record }); fireEvent.click(screen.getByRole("button", { name: "重新读取当前审核" }));
  await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(3));
});
it("retains exactly the submitted command for a lost receipt retry", async () => {
  const record = show(); vi.mocked(submitGroupRuleReviewAction).mockResolvedValueOnce({ ok: false, kind: "unavailable", error: "丢失" }).mockResolvedValueOnce({ ok: true, value: record });
  fireEvent.change(screen.getByLabelText("审核决定"), { target: { value: "REJECT" } }); fireEvent.change(screen.getByLabelText("审核说明"), { target: { value: "需重查" } });
  fireEvent.click(screen.getByRole("button", { name: "提交独立审核" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "重试原提交（相同请求）" })).toBeVisible());
  expect(screen.queryByRole("article")).not.toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "重试原提交（相同请求）" }));
  await waitFor(() => expect(submitGroupRuleReviewAction).toHaveBeenCalledTimes(2));
  expect(vi.mocked(submitGroupRuleReviewAction).mock.calls[0]).toEqual(vi.mocked(submitGroupRuleReviewAction).mock.calls[1]);
});
it("loads the saved route dynamically", async () => {
  vi.mocked(loadGroupRuleReviewAction).mockResolvedValue({ ok: false, kind: "stale", error: "已过期" });
  render(await SavedPage({ params: Promise.resolve({ taskId: "task", prepId: "prep" }) }));
  expect(dynamic).toBe("force-dynamic"); expect(loadGroupRuleReviewAction).toHaveBeenCalledWith("task", "prep"); expect(screen.getByRole("alert")).toHaveTextContent("已过期");
});
