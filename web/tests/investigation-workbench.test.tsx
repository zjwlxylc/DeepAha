import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import WorkbenchShell from "../components/investigations/workbench-shell";
import { bindingTarget, preparedDocuments, ruleReadyTask, factPreparation, task } from "./investigations-fixture";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

describe("object workbench", () => {
  it("does not replace a whole binding from a single-object form", () => {
    render(<WorkbenchShell task={{ ...ruleReadyTask(), document_preparation: preparedDocuments, workbench: { entity_id: "position-1", offset: 0, total: 1 } }} step="identity" queue="" targets={[bindingTarget]} />);
    expect(screen.queryByRole("combobox", { name: "关联到已有机会" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "修订完整岗位归属" })).toHaveAttribute("href", `/review/investigations/${task.task_id}#investigation-binding-title`);
    expect(screen.getByText("登记尚无身份的岗位")).toBeInTheDocument();
  });
  it("requires an explicit object without defaulting to the first position", () => {
    render(<WorkbenchShell task={{ ...task, workbench: { entity_id: null, offset: 0, total: 0 }, facts: [] }} step="facts" queue="q=notice" targets={[]} />);
    expect(screen.getByText(/系统不会自动替你选择/)).toBeVisible();
    expect(screen.getByRole("link", { name: "教学岗位（P001）" })).toHaveAttribute("href", expect.stringContaining("entity_id=position-1"));
    expect(screen.queryByRole("combobox", { name: "字段决定" })).not.toBeInTheDocument();
  });
  it("keeps the whole-object promotion gate while displaying one field", () => {
    const preparation = { ...factPreparation, rows: [factPreparation.rows[0]], slice: { entity_id: "position-1", offset: 0, total: 2500, candidate_total: 2499, can_promote: false } };
    render(<WorkbenchShell task={{ ...task, workbench: { entity_id: "position-1", offset: 0, total: 2500 }, fact_review: { current: preparation, history: [] } }} step="facts" queue="" targets={[]} />);
    expect(screen.getByText(/共 2500 个原始字段/)).toBeVisible();
    expect(screen.getByRole("link", { name: "下一个字段" })).toHaveAttribute("href", expect.stringContaining("offset=1"));
    expect(screen.queryByRole("button", { name: "保存审核事实集" })).not.toBeInTheDocument();
  });
  it("reads the existing material decision without offering another approval", () => {
    render(<WorkbenchShell task={{ ...task, review: { decision: "APPROVE", reason: "原始理由保持不变", reviewer_id: "reviewer", created_at: task.updated_at } }} step="materials" queue="" targets={[]} />);
    expect(screen.getByText("原始理由保持不变")).toBeVisible();
    expect(screen.queryByRole("button", { name: "记录内部材料审核" })).not.toBeInTheDocument();
  });
});
