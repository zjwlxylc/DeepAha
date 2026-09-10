import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import CrossLevel from "../components/investigations/cross-level";
import { loadCrossLevelAction } from "../app/review/investigations/cross-level-actions";
import fixture from "./cross-level-fixture.json";
import type { CrossLevelReview, RawCondition } from "../lib/cross-level";
import Page from "../app/review/investigations/[taskId]/unit-plans/[planId]/cross-level/page";
vi.mock("../app/review/investigations/cross-level-actions", () => ({ loadCrossLevelAction: vi.fn() }));
const value = fixture as CrossLevelReview;
const taskId = value.dependencies.group.dependencies.group_source.source.task_id, planId = value.dependencies.group.snapshot.base_v2.plan_id;
beforeEach(() => { vi.mocked(loadCrossLevelAction).mockReset(); });
it("keeps distinct original conditions and quotes attached to their source scope", () => {
  const v = structuredClone(value), group = v.dependencies.group.dependencies.group_source.source.source_group;
  const ann = v.dependencies.announcement.dependencies.announcement_sources[0].source_rows[0].original;
  const grouped = (group.unit_level as RawCondition[])[0];
  const unit = (group.positions[0].facts as RawCondition[])[0];
  for (const [raw, label] of [[ann, "公告独有"], [grouped, "组独有"], [unit, "岗位独有"]] as const) {
    raw.field = label; raw.value = `${label}条件`; raw.evidence![0].quote = `${label}原文`;
  }
  render(<CrossLevel taskId={taskId} planId={planId} initialResult={{ ok: true, value: v }} />);
  for (const label of ["公告独有", "组独有", "岗位独有"]) {
    const article = screen.getByRole("heading", { name: label }).closest("article")!;
    expect(article).toHaveTextContent(`${label}原文`);
    expect(article).toHaveTextContent(`${label}条件`);
    expect(article.querySelectorAll("blockquote")[0]).toHaveTextContent(`${label}原文`);
  }
});
it("shows all three scopes, excluded and unresolved rows, evidence and no approval controls", () => {
  render(<CrossLevel taskId={taskId} planId={planId} initialResult={{ ok: true, value }} />);
  expect(screen.getAllByRole("article")).toHaveLength(4);
  expect(screen.getByText("全部条件 4 项 · 岗位层 1 · 继承范围 1 · 明确不适用 1 · 待处理 1")).toBeVisible();
  expect(screen.getByText(/未判断累积、例外或冲突/)).toBeVisible();
  expect(screen.getByText(/不是资格结论/)).toBeVisible();
  expect(screen.getAllByRole("link", { name: /下载原件/ })).toHaveLength(4);
  expect(screen.queryByRole("button", { name: /批准|保存|提交/ })).not.toBeInTheDocument();
  for (const link of screen.getAllByRole("link").filter(a => a.getAttribute("href")?.startsWith("#"))) {
    const target = decodeURIComponent(link.getAttribute("href")!.slice(1));
    expect(document.getElementById(target)).not.toBeNull();
  }
});
it.each(["stale", "forbidden", "unavailable"] as const)("hides old conditions and review groups during reload and after %s", async kind => {
  vi.mocked(loadCrossLevelAction).mockResolvedValue({ ok: false, kind, error: "不可用" });
  render(<CrossLevel taskId={taskId} planId={planId} initialResult={{ ok: true, value }} />);
  fireEvent.click(screen.getByRole("button", { name: "重新读取当前预览" }));
  expect(screen.queryByRole("article")).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "同字段跨层级关系" })).not.toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("alert")).toBeVisible());
  vi.mocked(loadCrossLevelAction).mockResolvedValue({ ok: true, value });
  fireEvent.click(screen.getByRole("button", { name: "重新读取当前预览" }));
  await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(4));
});
it("remounts after same-address server refresh and removes stale content", async () => {
  const params = Promise.resolve({ taskId, planId });
  vi.mocked(loadCrossLevelAction).mockResolvedValue({ ok: true, value });
  const { rerender } = render(await Page({ params }));
  expect(screen.getAllByRole("article")).toHaveLength(4);
  vi.mocked(loadCrossLevelAction).mockResolvedValue({ ok: false, kind: "forbidden", error: "撤权" });
  rerender(await Page({ params }));
  expect(screen.getByRole("alert")).toHaveTextContent("撤权");
  expect(screen.queryByRole("article")).not.toBeInTheDocument();
});
