import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import fixture from "./group-applicability-fixture.json";
import type { GroupApplicabilityReviewView } from "../lib/group-applicability-decisions";
import GroupApplicability from "../components/investigations/group-applicability";
import { loadGroupApplicabilityReview, saveGroupApplicabilityDecision } from "../app/review/investigations/group-applicability-decision-actions";
vi.mock("../app/review/investigations/group-applicability-decision-actions", () => ({ loadGroupApplicabilityReview: vi.fn(), saveGroupApplicabilityDecision: vi.fn() }));
const value = { ...fixture, decisions: { ...fixture, scope: "GROUP_APPLICABILITY_REVIEW_ONLY", history: [], latest: null } } as unknown as GroupApplicabilityReviewView;
describe("group applicability context page", () => {
  it("identifies only the selected rule when a group contains multiple fields", () => {
    const second = structuredClone(value);
    const rows = second.source_review.result.preview.result.fact_review.result.rows;
    rows[1].original_field = "户籍要求";
    second.candidate.source_index = rows[1].source_index;
    render(<GroupApplicability identity={second.context} initial={{ ok: true, value: second }} />);
    expect(screen.getByRole("heading", { name: "本次审核的组规则：户籍要求" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "本次审核的组规则：学历要求" })).not.toBeInTheDocument();
  });
  it("preserves fields, evidence and uncertainty with explicit undecided controls", () => {
    render(<GroupApplicability identity={value.context} initial={{ ok: true, value }} />);
    expect(screen.getByRole("heading", { name: "尚未处理条件" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "完整成员清单" })).toBeVisible();
    expect(screen.getByText(/适用决定不自动继承规则/)).toBeVisible();
    expect(screen.getByRole("combobox")).toHaveValue("");
    expect(screen.getAllByRole("link", { name: /下载原件/ })).toHaveLength(value.evidence_options.length);
  });
  it("immediately hides old evidence during refresh and keeps it hidden on failure", async () => {
    let finish!: (result: { ok: false; error: string }) => void;
    vi.mocked(loadGroupApplicabilityReview).mockReturnValue(new Promise(resolve => { finish = resolve; }));
    render(<GroupApplicability identity={value.context} initial={{ ok: true, value }} />);
    fireEvent.click(screen.getByRole("button", { name: "重新读取当前上下文" }));
    expect(screen.queryByRole("heading", { name: "当前官方原文" })).not.toBeInTheDocument();
    finish({ ok: false, error: "证据已过期" });
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("证据已过期"));
    expect(screen.queryByRole("heading", { name: "组条件与成员" })).not.toBeInTheDocument();
  });
  it("rejects a different context while paging", async () => {
    const paged = { ...value, next_cursor: `${value.evidence_options[0].block_id}:${value.evidence_options[0].member_id}` };
    vi.mocked(loadGroupApplicabilityReview).mockResolvedValue({ ok: true, value: { ...value, context_hash: "a".repeat(64) } });
    render(<GroupApplicability identity={value.context} initial={{ ok: true, value: paged }} />);
    fireEvent.click(screen.getByRole("button", { name: "读取下一页原文" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("上下文已变化"));
    expect(screen.queryByRole("heading", { name: "当前官方原文" })).not.toBeInTheDocument();
  });
  it("requires literal evidence and hides the form while saving", async () => {
    vi.mocked(saveGroupApplicabilityDecision).mockReturnValue(new Promise(() => {}));
    render(<GroupApplicability identity={value.context} initial={{ ok: true, value }} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "APPLIES" } });
    fireEvent.change(screen.getByLabelText("决定理由"), { target: { value: "Synthetic review" } });
    fireEvent.click(screen.getByRole("button", { name: "保存适用性决定" }));
    expect(saveGroupApplicabilityDecision).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("checkbox", { name: "引用原文 1" }));
    fireEvent.click(screen.getByRole("button", { name: "保存适用性决定" }));
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(saveGroupApplicabilityDecision).toHaveBeenCalledOnce();
  });
});
