import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RuleApplicabilityReview from "../components/investigations/rule-applicability-review";
import { loadRuleApplicabilityAction, saveRuleApplicabilityAction } from "../app/review/investigations/rule-applicability-actions";
import { unitSnapshotFixture } from "./investigations-fixture";
import { applicabilityDecisionFixture, applicabilityIds, applicabilityViewFixture } from "./rule-applicability-fixture";

vi.mock("../app/review/investigations/rule-applicability-actions", () => ({ loadRuleApplicabilityAction: vi.fn(), saveRuleApplicabilityAction: vi.fn() }));
const fixture = () => applicabilityViewFixture(unitSnapshotFixture());
function mount(view = fixture().view) {
  const { identity } = fixture();
  render(<RuleApplicabilityReview identity={identity} initialView={view} requestKey={applicabilityIds.member} />);
  return { identity, view };
}
function fill(outcome = "APPLIES") {
  fireEvent.change(screen.getByLabelText("适用性决定"), { target: { value: outcome } });
  fireEvent.change(screen.getByLabelText("决定理由"), { target: { value: "  原文明确说明全部岗位。\n" } });
  if (outcome !== "NEEDS_ADJUDICATION") fireEvent.click(screen.getByLabelText("引用原文 1"));
}
beforeEach(() => { vi.resetAllMocks(); });
describe("applicability review", () => {
  it("separates source and target, requires an explicit outcome and retains uncertainty", () => {
    mount();
    expect(screen.getByRole("heading", { name: "来源公告" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "目标岗位" })).toBeVisible();
    expect(screen.getByText("示例招聘公告")).toBeVisible();
    expect(screen.getByText("教学岗位")).toBeVisible();
    expect(screen.getByLabelText("适用性决定")).toHaveValue("");
    expect(screen.getByText(/不解除整体 UNCERTAIN/)).toBeVisible();
    expect(screen.getByLabelText("引用原文 1")).not.toBeChecked();
  });
  it("locks the exact request after a lost receipt, refreshes before allowing a correction and rotates the nonce", async () => {
    const { identity, view } = mount(), receipt = applicabilityDecisionFixture(view);
    vi.mocked(saveRuleApplicabilityAction).mockResolvedValueOnce({ ok: false, kind: "unavailable", error: "暂未取得最新回执" }).mockResolvedValue({ ok: true, value: receipt });
    vi.mocked(loadRuleApplicabilityAction).mockResolvedValue({ ok: true, value: { ...view, latest: receipt, history: [receipt] } });
    fill(); fireEvent.click(screen.getByRole("button", { name: "保存适用性决定" }));
    await screen.findByRole("button", { name: "重试原请求" });
    expect(screen.getByLabelText("决定理由")).toBeDisabled();
    expect(screen.getByRole("button", { name: "加载更多原文" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "重试原请求" }));
    await waitFor(() => expect(screen.getByLabelText("适用性决定")).toHaveValue(""));
    const [first, retry] = vi.mocked(saveRuleApplicabilityAction).mock.calls;
    expect(retry).toEqual(first);
    expect(first[0]).toEqual(identity);
    expect(first[1].previous_decision_id).toBeNull();
    expect(first[1].evidence[0].quote).toBe(view.evidence_options[0].text);
    expect(first[1].reason).toBe("  原文明确说明全部岗位。\n");
    fill("DOES_NOT_APPLY"); fireEvent.click(screen.getByRole("button", { name: "保存适用性决定" }));
    await waitFor(() => expect(saveRuleApplicabilityAction).toHaveBeenCalledTimes(3));
    const third = vi.mocked(saveRuleApplicabilityAction).mock.calls[2];
    expect(third[1].previous_decision_id).toBe(receipt.decision_id);
    expect(third[2]).not.toBe(first[2]);
  });
  it("keeps distinct members sharing one block when paging and preserves selected quotes", async () => {
    const { identity, view } = mount();
    fireEvent.click(screen.getByLabelText("引用原文 1"));
    const second = { ...view.evidence_options[0], member_id: applicabilityIds.secondBlock, material_id: "another-material" };
    vi.mocked(loadRuleApplicabilityAction).mockResolvedValue({ ok: true, value: { ...view, evidence_options: [second], next_cursor: null } });
    fireEvent.click(screen.getByRole("button", { name: "加载更多原文" }));
    await screen.findByLabelText("引用原文 2");
    expect(loadRuleApplicabilityAction).toHaveBeenCalledWith(identity, view.next_cursor);
    expect(screen.getByLabelText("引用原文 1")).toBeChecked();
    expect(screen.getByLabelText("引用文字 1")).toHaveValue(view.evidence_options[0].text);
    expect(screen.getByText("已加载当前可引用的全部原文块，共 2 块。")).toBeVisible();
  });
  it.each(["context", "latest"])("hides old evidence when paging finds a changed %s", async changed => {
    const { view } = mount();
    vi.mocked(loadRuleApplicabilityAction).mockResolvedValue({ ok: true, value: { ...view, ...(changed === "context" ? { context_hash: "f".repeat(64) } : { latest: applicabilityDecisionFixture(view) }) } });
    fireEvent.click(screen.getByRole("button", { name: "加载更多原文" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("已变化");
    expect(screen.queryByLabelText("引用原文 1")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存适用性决定" })).not.toBeInTheDocument();
  });
  it("allows a reasoned unresolved decision without evidence", async () => {
    const { view } = mount(), receipt = applicabilityDecisionFixture(view, { outcome: "NEEDS_ADJUDICATION", evidence: [] });
    vi.mocked(saveRuleApplicabilityAction).mockResolvedValue({ ok: true, value: receipt });
    vi.mocked(loadRuleApplicabilityAction).mockResolvedValue({ ok: true, value: { ...view, latest: receipt, history: [receipt] } });
    fill("NEEDS_ADJUDICATION"); fireEvent.click(screen.getByRole("button", { name: "保存适用性决定" }));
    await waitFor(() => expect(saveRuleApplicabilityAction).toHaveBeenCalledTimes(1));
    expect(vi.mocked(saveRuleApplicabilityAction).mock.calls[0][1].evidence).toEqual([]);
  });
  it("rejects a quote absent from the displayed original text", async () => {
    mount(); fill();
    fireEvent.change(screen.getByLabelText("引用文字 1"), { target: { value: "不存在于原文的结论" } });
    fireEvent.click(screen.getByRole("button", { name: "保存适用性决定" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("字面片段");
    expect(saveRuleApplicabilityAction).not.toHaveBeenCalled();
  });
  it("hides old evidence if the receipt succeeds but reloading latest fails", async () => {
    const { view } = mount();
    vi.mocked(saveRuleApplicabilityAction).mockResolvedValue({ ok: true, value: applicabilityDecisionFixture(view) });
    vi.mocked(loadRuleApplicabilityAction).mockResolvedValue({ ok: false, kind: "forbidden", error: "当前会话没有适用性审阅权限" });
    fill(); fireEvent.click(screen.getByRole("button", { name: "保存适用性决定" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("当前会话没有");
    expect(screen.queryByText("示例招聘公告")).not.toBeInTheDocument();
  });
  it("shows empty evidence without fabricating a supported decision", () => {
    mount({ ...fixture().view, evidence_options: [], next_cursor: null });
    expect(screen.getByText("当前没有可引用的原文块。可记录待裁决及理由。")).toBeVisible();
    expect(screen.getByLabelText("适用性决定")).toHaveValue("");
  });
  it("links the exact member official source and private original", () => {
    const view = fixture().view;
    mount(view);
    expect(screen.getByRole("link", { name: "查看官方原文" })).toHaveAttribute("href", "https://example.test/notices/announcement.html");
    expect(screen.getByRole("link", { name: "打开对应原件" })).toHaveAttribute("href", expect.stringContaining(view.evidence_options[0].material_id));
  });
  it.each(["javascript:alert(1)", "https://user:secret@example.test/notice"])("does not render unsafe official URL %s", url => {
    const view = fixture().view;
    mount({ ...view, evidence_options: [{ ...view.evidence_options[0], source_url: url }] });
    expect(screen.queryByRole("link", { name: "查看官方原文" })).not.toBeInTheDocument();
    expect(screen.getByText("官方地址不可用")).toBeVisible();
  });
});
