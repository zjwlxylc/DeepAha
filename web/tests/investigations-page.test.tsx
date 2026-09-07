import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InvestigationsPage from "../app/review/investigations/page";
import InvestigationPage from "../app/review/investigations/[taskId]/page";
import { getInvestigations, getInvestigationSources, getInvestigation } from "../lib/investigations";
import { source, task, taskId } from "./investigations-fixture";

vi.mock("../lib/investigations", async (original) => ({
  ...await original<typeof import("../lib/investigations")>(),
  getInvestigations: vi.fn(), getInvestigationSources: vi.fn(), getInvestigation: vi.fn(),
}));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

describe("investigation pages", () => {
  beforeEach(() => {
    vi.mocked(getInvestigations).mockResolvedValue({ tasks: [] });
    vi.mocked(getInvestigationSources).mockResolvedValue({ sources: [source] });
    vi.mocked(getInvestigation).mockResolvedValue(task);
  });
  it("registers tasks without a live execution control", async () => {
    render(await InvestigationsPage());
    expect(screen.getByRole("button", { name: "登记调查任务" })).toBeVisible();
    expect(screen.getByText(/登记不会访问官网或调用调查服务/)).toBeVisible();
    expect(screen.getByText("还没有调查任务")).toBeVisible();
    expect(screen.queryByRole("button", { name: /执行|恢复|开始调查/ })).not.toBeInTheDocument();
  });
  it("shows hierarchy, field evidence, attachment downloads and honest review semantics", async () => {
    render(await InvestigationPage({ params: Promise.resolve({ taskId }) }));
    expect(screen.getByRole("heading", { name: "示例招聘公告" })).toBeVisible();
    expect(screen.getByText("示例学院")).toBeVisible();
    expect(screen.getAllByText(/教学岗位/).length).toBeGreaterThan(0);
    expect(screen.getByText("学历要求：硕士及以上")).toBeVisible();
    expect(screen.getByText(/岗位表.*5.*D/)).toBeVisible();
    expect(screen.getAllByRole("link", { name: /下载原件/ })[0]).toHaveAttribute("href", `/review/investigations/${taskId}/materials/attachment-1`);
    expect(screen.getByText(/不等于正式机会、资格规则或公开目录发布/)).toBeVisible();
    expect(screen.getByRole("button", { name: "记录内部材料审核" })).toBeVisible();
    expect(screen.getByRole("combobox", { name: "审核决定" })).toHaveValue("REJECT");
  });
  it.each(["QUEUED", "APPROVED", "FAILED_VALIDATION"])("does not offer review in %s", async (status) => {
    vi.mocked(getInvestigation).mockResolvedValue({ ...task, status });
    render(await InvestigationPage({ params: Promise.resolve({ taskId }) }));
    expect(screen.queryByRole("button", { name: "记录内部材料审核" })).not.toBeInTheDocument();
  });
  it("shows a model note as candidate text alongside the field and official evidence", async () => {
    const note = "工作地点仅根据单位名称推断；<script>请核对</script>";
    vi.mocked(getInvestigation).mockResolvedValue({ ...task, facts: [{ ...task.facts[0], note }] });
    render(await InvestigationPage({ params: Promise.resolve({ taskId }) }));
    expect(screen.getByText("调查备注（待人工核对）")).toBeVisible();
    expect(screen.getByText(note)).toBeVisible();
    expect(screen.getByText(note).querySelector("script")).toBeNull();
    expect(screen.getByText("候选认为有依据")).toBeVisible();
    expect(screen.getByText("学历要求：硕士及以上")).toBeVisible();
  });
  it.each([null, undefined, ""])("does not invent a note when absent (%s)", async (note) => {
    vi.mocked(getInvestigation).mockResolvedValue({ ...task, facts: [{ ...task.facts[0], note }] });
    render(await InvestigationPage({ params: Promise.resolve({ taskId }) }));
    expect(screen.queryByText("调查备注（待人工核对）")).not.toBeInTheDocument();
  });
  it.each([
    ["WMA_REMOTE_REFUSED", "调查服务拒绝了本次执行"],
    ["WMA_OUTPUT_LIMIT_REACHED", "调查达到输出长度上限"],
    ["WMA_REQUEST_LIMIT_REACHED", "调查达到单轮请求上限"],
    ["WMA_REMOTE_CANCELLED", "调查服务已取消本次执行"],
    ["WMA_NON_SUCCESS_STOP", "调查没有正常结束"],
  ])("explains %s without offering review or automatically restarting", async (error_code, explanation) => {
    vi.mocked(getInvestigation).mockResolvedValue({ ...task, status: "EXECUTION_UNCERTAIN", error_code, issues: [] });
    render(await InvestigationPage({ params: Promise.resolve({ taskId }) }));
    expect(screen.getByText(new RegExp(explanation))).toBeVisible();
    expect(screen.getByText(/不会自动重新调查/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "记录内部材料审核" })).not.toBeInTheDocument();
  });
});
