import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InvestigationsPage from "../app/review/investigations/page";
import InvestigationPage from "../app/review/investigations/[taskId]/page";
import { getInvestigations, getInvestigationSources, getInvestigation, getInvestigationBindingTargets } from "../lib/investigations";
import { source, task, taskId, preparedDocuments, bindingTarget, evidenceCheck } from "./investigations-fixture";

vi.mock("../lib/investigations", async (original) => ({
  ...await original<typeof import("../lib/investigations")>(),
  getInvestigations: vi.fn(), getInvestigationSources: vi.fn(), getInvestigation: vi.fn(), getInvestigationBindingTargets: vi.fn(),
}));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

describe("investigation pages", () => {
  it("does not invent new verification dimensions from a historical boolean", async () => {
    render(await InvestigationPage({ params: Promise.resolve({ taskId }) }));
    expect(screen.getByText(/旧版回执：机械核验通过/)).toBeVisible();
    expect(screen.queryByText(/内容：找到原文/)).not.toBeInTheDocument();
  });
  it("separates found text, unsupported locator and missing persistent evidence", async () => {
    const check = structuredClone(evidenceCheck);
    check.verdict = "UNVERIFIED";
    check.counts = { PASS: 0, FAIL: 0, UNVERIFIED: 1 };
    Object.assign(check.references[0], { verdict: "UNVERIFIED", persistent_binding: null, binding_reason: "PERSISTENT_BINDING_UNAVAILABLE" });
    Object.assign(check.references[0].verification, { verdict: "UNVERIFIED", declared_locator: "UNSUPPORTED", binding: "UNBOUND" });
    vi.mocked(getInvestigation).mockResolvedValue({ ...task, evidence_check: check });
    render(await InvestigationPage({ params: Promise.resolve({ taskId }) }));
    expect(screen.getByText("内容：找到原文 · 定位：定位方式未支持")).toBeVisible();
    expect(screen.getByText("持久证据：尚未关联 · 待核验")).toBeVisible();
    expect(screen.getByText(/通过 0 \/ 失败 0 \/ 待核验 1/)).toBeVisible();
    expect(screen.queryByText(/旧版回执：机械核验通过/)).not.toBeInTheDocument();
  });
  beforeEach(() => {
    vi.mocked(getInvestigations).mockResolvedValue({ tasks: [] });
    vi.mocked(getInvestigationSources).mockResolvedValue({ sources: [source] });
    vi.mocked(getInvestigation).mockResolvedValue(task);
    vi.mocked(getInvestigationBindingTargets).mockResolvedValue({ targets: [bindingTarget] });
  });
  it("requires explicit identity selection after intake approval and full document preparation", async () => {
    vi.mocked(getInvestigation).mockResolvedValue({ ...task, status: "APPROVED", document_preparation: preparedDocuments });
    render(await InvestigationPage({ params: Promise.resolve({ taskId }) }));
    expect(screen.getByRole("combobox", { name: "关联到已有机会" })).toHaveValue("");
    expect(screen.getByRole("button", { name: "确认归属并冻结来源" })).toBeDisabled();
    expect(screen.getByText(/字段内容仍是候选/)).toBeVisible();
  });
  it("preserves pending identity when no existing target is available", async () => {
    vi.mocked(getInvestigation).mockResolvedValue({ ...task, status: "APPROVED", document_preparation: preparedDocuments });
    vi.mocked(getInvestigationBindingTargets).mockResolvedValue({ targets: [] });
    render(await InvestigationPage({ params: Promise.resolve({ taskId }) }));
    expect(screen.getByText(/目前没有可选择的机会版本/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "确认归属并冻结来源" })).not.toBeInTheDocument();
  });
  it("offers explicit local evidence preparation with an honest boundary", async () => {
    render(await InvestigationPage({ params: Promise.resolve({ taskId }) }));
    expect(screen.getByRole("button", { name: "准备文档证据" })).toBeVisible();
    expect(screen.getByText(/只解析已回收的原件/)).toBeVisible();
  });
  it("keeps failed and unsupported documents visible in the denominator", async () => {
    vi.mocked(getInvestigation).mockResolvedValue({ ...task, document_preparation: {
      ...preparedDocuments, status: "NEEDS_ATTENTION", material_count: 3, prepared_count: 1,
      materials: [...preparedDocuments.materials,
        { ...preparedDocuments.materials[0], material_id: "legacy.doc", outcome: "UNSUPPORTED", block_count: 0, error_code: "DOCUMENT_FORMAT_UNSUPPORTED" },
        { ...preparedDocuments.materials[0], material_id: "empty.pdf", outcome: "FAILED", block_count: 0, error_code: "PDF_TEXT_EMPTY" }],
    } });
    render(await InvestigationPage({ params: Promise.resolve({ taskId }) }));
    expect(screen.getByText("1 / 3 份材料已完成文档证据准备。")).toBeVisible();
    expect(screen.getByText("格式尚不支持，保留原件待处理")).toBeVisible();
    expect(screen.getByText("解析失败")).toBeVisible();
    expect(screen.getByText(/仍有未准备、需复核或不支持/)).toBeVisible();
    expect(screen.getByRole("button", { name: "记录内部材料审核" })).toBeVisible();
  });
  it.each(["QUEUED", "REJECTED", "EXPIRED"])("does not offer document preparation in %s", async (status) => {
    vi.mocked(getInvestigation).mockResolvedValue({ ...task, status });
    render(await InvestigationPage({ params: Promise.resolve({ taskId }) }));
    expect(screen.queryByRole("button", { name: "准备文档证据" })).not.toBeInTheDocument();
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
