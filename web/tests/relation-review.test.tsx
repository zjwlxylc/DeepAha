import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import RelationReview from "../components/investigations/relation-review";
import { decideRelation, loadRelation } from "../app/review/investigations/relation-actions";
import type { RelationView } from "../lib/relation-review";
import type { CrossLevelReview } from "../lib/cross-level";
import source from "./cross-level-fixture.json";
vi.mock("../app/review/investigations/relation-actions", () => ({ decideRelation: vi.fn(), loadRelation: vi.fn() }));
const view: RelationView = { proposal_id: "p", proposal_payload_sha256: "a", payload_sha256: "b", package: {
  proposal: { proposal_id: "p", producer_id: "producer", relation: "CUMULATIVE", reason: "原始提案理由",
    source_review: source as CrossLevelReview, condition_ids: [], displaced_condition_ids: [],
    evidence: [{ quote: "官方条件原文", source_url: "https://official.example/notice", locator: { row: 1 }, purpose: "RELATION" }] }, decisions: [] },
  review: { proposal_id: "p", status: "UNREVIEWED", latest: null, executable: false, overall_qualification: "UNCERTAIN" } };
beforeEach(() => { vi.clearAllMocks(); });
it("hides old evidence on failed writes and retries the exact request and nonce", async () => {
  vi.mocked(decideRelation).mockResolvedValue({ ok: false, error: "回执不可用" });
  render(<RelationReview task="t" plan="u" id="p" initial={{ ok: true, value: view }} />);
  fireEvent.change(screen.getByLabelText("审核理由"), { target: { value: "需要核对例外" } });
  fireEvent.click(screen.getByRole("button", { name: "追加审核记录" }));
  await screen.findByRole("alert");
  expect(screen.queryByText("官方条件原文")).not.toBeInTheDocument();
  const first = vi.mocked(decideRelation).mock.calls[0];
  vi.mocked(loadRelation).mockResolvedValue({ ok: false, error: "重读也失败" });
  fireEvent.click(screen.getByRole("button", { name: "重新读取当前状态" }));
  await screen.findByText("重读也失败");
  fireEvent.click(screen.getByRole("button", { name: "重试原请求" }));
  await waitFor(() => expect(decideRelation).toHaveBeenCalledTimes(2));
  expect(vi.mocked(decideRelation).mock.calls[1]).toEqual(first);
});
it("keeps stale history visible but removes decision controls", () => {
  render(<RelationReview task="t" plan="u" id="p" initial={{ ok: true, value: { ...view, review: { ...view.review, status: "STALE" } } }} />);
  expect(screen.getByText("官方条件原文")).toBeVisible();
  expect(screen.queryByRole("button", { name: "追加审核记录" })).not.toBeInTheDocument();
});
it("clears old content when current read fails", async () => {
  vi.mocked(loadRelation).mockResolvedValue({ ok: false, error: "权限失效" });
  render(<RelationReview task="t" plan="u" id="p" initial={{ ok: true, value: view }} />);
  fireEvent.click(screen.getByRole("button", { name: "重新读取当前状态" }));
  await screen.findByText("权限失效");
  expect(screen.queryByText("原始提案理由")).not.toBeInTheDocument();
});
