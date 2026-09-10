import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import ProposalForm from "../components/investigations/relation-proposal";
import { loadProposalContext, proposeRelation } from "../app/review/investigations/proposal-actions";
import type { ProposalContext } from "../lib/relation-proposal";
import f from "./relation-review-fixture.json";
import n from "./relation-proposal-fixture.json";
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("../app/review/investigations/proposal-actions", () => ({ loadProposalContext: vi.fn(), proposeRelation: vi.fn() }));
const p = f.saved.package.proposal;
const context = { task_id: f.task, target_plan_id: f.plan, review_hash: p.source_review_hash, review: p.source_review, evidence_options: [], next_cursor: null } as ProposalContext;
beforeEach(() => { vi.clearAllMocks(); });
function choose() {
  for (const id of p.condition_ids) fireEvent.click(screen.getByLabelText(`选择条件 ${id}`));
  fireEvent.change(screen.getByLabelText("提案理由"), { target: { value: "需要核对关系" } });
}
it("requires cross-scope selection and evidence before a resolved relation", () => {
  render(<ProposalForm task={f.task} plan={f.plan} initial={{ ok: true, value: context }} />);
  expect(screen.getByRole("button", { name: "保存关系提案" })).toBeDisabled();
  choose();
  expect(screen.getByRole("button", { name: "保存关系提案" })).toBeEnabled();
  fireEvent.change(screen.getByLabelText("关系类型"), { target: { value: "CUMULATIVE" } });
  expect(screen.getByRole("button", { name: "保存关系提案" })).toBeDisabled();
});
it("hides failed source and retries identical command and nonce after failed reread", async () => {
  vi.mocked(proposeRelation).mockResolvedValue({ ok: false, error: "回执未知" });
  vi.mocked(loadProposalContext).mockResolvedValue({ ok: false, error: "权限失效" });
  render(<ProposalForm task={f.task} plan={f.plan} initial={{ ok: true, value: context }} />);
  choose(); fireEvent.click(screen.getByRole("button", { name: "保存关系提案" }));
  await screen.findByText("回执未知");
  expect(screen.queryByLabelText("提案理由")).not.toBeInTheDocument();
  const first = vi.mocked(proposeRelation).mock.calls[0];
  fireEvent.click(screen.getByRole("button", { name: "重新读取当前条件" }));
  await screen.findByText("权限失效");
  fireEvent.click(screen.getByRole("button", { name: "重试原请求" }));
  await waitFor(() => expect(proposeRelation).toHaveBeenCalledTimes(2));
  expect(vi.mocked(proposeRelation).mock.calls[1]).toEqual(first);
});
it("navigates to the stable saved proposal address", async () => {
  vi.mocked(proposeRelation).mockResolvedValue({ ok: true, value: f.saved as never });
  render(<ProposalForm task={f.task} plan={f.plan} initial={{ ok: true, value: context }} />);
  choose(); fireEvent.click(screen.getByRole("button", { name: "保存关系提案" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith(expect.stringContaining(`?proposal=${f.saved.proposal_id}`)));
});
it("requires a proper exception subset and clears evidence when selection changes", () => {
  render(<ProposalForm task={n.task} plan={n.plan} initial={{ ok: true, value: n.context as ProposalContext }} />);
  for (const id of n.command.condition_ids) fireEvent.click(screen.getByLabelText(`选择条件 ${id}`));
  fireEvent.change(screen.getByLabelText("提案理由"), { target: { value: n.command.reason } });
  fireEvent.change(screen.getByLabelText("关系类型"), { target: { value: "EXCEPTION" } });
  const e = n.command.evidence[0];
  fireEvent.change(screen.getByLabelText("官方原文块"), { target: { value: `${e.block_id}:${e.member_id}` } });
  fireEvent.change(screen.getByLabelText("逐字引文"), { target: { value: "非逐字近似条件" } });
  expect(screen.getByRole("button", { name: "添加证据" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("逐字引文"), { target: { value: e.quote } });
  const coverage = screen.getByRole("group", { name: "此引文支持的条件" });
  for (const checkbox of coverage.querySelectorAll("input")) fireEvent.click(checkbox);
  fireEvent.click(screen.getByRole("button", { name: "添加证据" }));
  fireEvent.change(screen.getByLabelText("证据用途"), { target: { value: "RELATION" } });
  fireEvent.click(screen.getByRole("button", { name: "添加证据" }));
  const submit = screen.getByRole("button", { name: "保存关系提案" });
  expect(submit).toBeDisabled();
  const displaced = screen.getByRole("group", { name: "被例外替代的条件（至少一条，不能为全部）" }).querySelectorAll("input");
  fireEvent.click(displaced[0]); expect(submit).toBeEnabled();
  for (const checkbox of [...displaced].slice(1)) fireEvent.click(checkbox);
  expect(submit).toBeDisabled();
  fireEvent.click(screen.getByLabelText(`选择条件 ${n.command.condition_ids[0]}`));
  expect(screen.queryByRole("button", { name: "移除证据 1" })).not.toBeInTheDocument();
});
it("fails closed if source changes while loading another evidence page", async () => {
  const paged = { ...context, next_cursor: "next" };
  vi.mocked(loadProposalContext).mockResolvedValue({ ok: true, value: { ...context, review_hash: "different" } });
  render(<ProposalForm task={f.task} plan={f.plan} initial={{ ok: true, value: paged }} />);
  fireEvent.click(screen.getByRole("button", { name: "加载更多原文块" }));
  await screen.findByRole("alert");
  expect(screen.queryByLabelText("提案理由")).not.toBeInTheDocument();
  expect(proposeRelation).not.toHaveBeenCalled();
});
