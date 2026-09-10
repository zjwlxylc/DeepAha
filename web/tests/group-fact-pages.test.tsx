import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import StartPage, { dynamic as startDynamic } from "../app/review/investigations/[taskId]/group-bindings/[recordId]/facts/page";
import RecordPage, { dynamic as recordDynamic } from "../app/review/investigations/[taskId]/group-facts/[prepId]/page";
import { loadGroupFactStartAction, loadGroupFactRecordAction, submitGroupFactAction } from "../app/review/investigations/group-fact-actions";
vi.mock("../app/review/investigations/group-fact-actions", () => ({ loadGroupFactStartAction: vi.fn(), loadGroupFactRecordAction: vi.fn(), submitGroupFactAction: vi.fn() }));
it("loads the exact group dynamically without preparing on GET", async () => {
  vi.mocked(loadGroupFactStartAction).mockResolvedValue({ ok: false, kind: "stale", error: "来源已变化" });
  render(await StartPage({ params: Promise.resolve({ taskId: "task", recordId: "group" }) }));
  expect(startDynamic).toBe("force-dynamic"); expect(loadGroupFactStartAction).toHaveBeenCalledWith("task", "group"); expect(submitGroupFactAction).not.toHaveBeenCalled(); expect(screen.getByRole("alert")).toBeVisible();
});
it("loads the exact preparation dynamically and hides unavailable content", async () => {
  vi.mocked(loadGroupFactRecordAction).mockResolvedValue({ ok: false, kind: "forbidden", error: "没有权限" });
  render(await RecordPage({ params: Promise.resolve({ taskId: "task", prepId: "prep" }) }));
  expect(recordDynamic).toBe("force-dynamic"); expect(loadGroupFactRecordAction).toHaveBeenCalledWith("task", "prep"); expect(screen.getByRole("alert")).toHaveTextContent("没有权限"); expect(screen.queryByRole("article")).not.toBeInTheDocument();
});
