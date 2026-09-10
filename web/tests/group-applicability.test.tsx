import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import fixture from "./group-applicability-fixture.json";
import type { GroupApplicabilityView } from "../lib/group-applicability";
import GroupApplicability from "../components/investigations/group-applicability";
import { loadGroupApplicabilityAction } from "../app/review/investigations/group-applicability-actions";
vi.mock("../app/review/investigations/group-applicability-actions", () => ({ loadGroupApplicabilityAction: vi.fn() }));
const value = fixture as GroupApplicabilityView;
describe("group applicability context page", () => {
  it("preserves fields, evidence and uncertainty without decision controls", () => {
    render(<GroupApplicability identity={value.context} initial={{ ok: true, value }} />);
    expect(screen.getByRole("heading", { name: "尚未处理条件" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "完整成员清单" })).toBeVisible();
    expect(screen.getByText(/岗位适用尚未裁决，不自动继承规则/)).toBeVisible();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /下载原件/ })).toHaveLength(value.evidence_options.length);
  });
  it("immediately hides old evidence during refresh and keeps it hidden on failure", async () => {
    let finish!: (result: { ok: false; error: string }) => void;
    vi.mocked(loadGroupApplicabilityAction).mockReturnValue(new Promise(resolve => { finish = resolve; }));
    render(<GroupApplicability identity={value.context} initial={{ ok: true, value }} />);
    fireEvent.click(screen.getByRole("button", { name: "重新读取当前上下文" }));
    expect(screen.queryByRole("heading", { name: "当前官方原文" })).not.toBeInTheDocument();
    finish({ ok: false, error: "证据已过期" });
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("证据已过期"));
    expect(screen.queryByRole("heading", { name: "组条件与成员" })).not.toBeInTheDocument();
  });
  it("rejects a different context while paging", async () => {
    const paged = { ...value, next_cursor: `${value.evidence_options[0].block_id}:${value.evidence_options[0].member_id}` };
    vi.mocked(loadGroupApplicabilityAction).mockResolvedValue({ ok: true, value: { ...value, context_hash: "a".repeat(64) } });
    render(<GroupApplicability identity={value.context} initial={{ ok: true, value: paged }} />);
    fireEvent.click(screen.getByRole("button", { name: "读取下一页原文" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("上下文已变化"));
    expect(screen.queryByRole("heading", { name: "当前官方原文" })).not.toBeInTheDocument();
  });
});
