import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import RelationQueue from "../components/investigations/relation-queue";
import { loadRelationQueue } from "../app/review/investigations/queue-actions";
import type { RelationQueueView } from "../lib/relation-queue";
vi.mock("../app/review/investigations/queue-actions", () => ({ loadRelationQueue: vi.fn() }));
const value: RelationQueueView = { task_id: "t", target_plan_id: "p", source_review_hash: "hash", read_at: "2026-09-11T01:00:00Z", executable: false, overall_qualification: "UNCERTAIN", next_after: "next", proposals: [
  { proposal_id: "one", created_at: "2026-09-11T00:00:00Z", relation: "CUMULATIVE", reason: "需要同时满足", condition_ids: ["a", "b"], status: "UNREVIEWED", is_own_proposal: true },
  { proposal_id: "two", created_at: "2026-09-11T00:00:01Z", relation: "CONFLICT", reason: "条件不一致", condition_ids: ["a", "c"], status: "STALE", is_own_proposal: false },
] };
it("filters only this page and keeps stable detail links and ownership visible", () => {
  render(<RelationQueue task="t" plan="p" initial={{ ok: true, value }} />);
  expect(screen.getByText("自己创建，需他人独立审核")).toBeVisible();
  expect(screen.getByRole("link", { name: "关系提案 1" })).toHaveAttribute("href", expect.stringContaining("?proposal=one"));
  fireEvent.change(screen.getByLabelText("筛选本页审核状态"), { target: { value: "STALE" } });
  expect(screen.queryByText("需要同时满足")).not.toBeInTheDocument();
  expect(screen.getByText("条件不一致")).toBeVisible();
  expect(screen.getByRole("button", { name: "读取下一页" })).toBeEnabled();
});
it("hides outdated approval on failed reread and can retry the same page", async () => {
  vi.mocked(loadRelationQueue).mockResolvedValue({ ok: false, error: "权限失效" });
  render(<RelationQueue task="t" plan="p" initial={{ ok: true, value }} />);
  fireEvent.click(screen.getByRole("button", { name: "读取下一页" }));
  await screen.findByText("权限失效");
  expect(screen.queryByText("条件不一致")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "重新读取本页" }));
  expect(vi.mocked(loadRelationQueue).mock.calls.at(-1)).toEqual(["t", "p", "next"]);
});
