import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import GroupRulePreview from "../components/investigations/group-rule-preview";
import Page, { dynamic } from "../app/review/investigations/[taskId]/group-facts/[prepId]/rules/page";
import { loadGroupRulePreviewAction } from "../app/review/investigations/group-rule-actions";
import { groupFactFixture } from "./group-fact-fixture";
import { groupRuleFixture } from "./group-rule-fixture";
import { groupSourceFixture, groupRecordFixture } from "./group-source-fixture";
import { ruleReadyTask } from "./investigations-fixture";
vi.mock("../app/review/investigations/group-rule-actions", () => ({ loadGroupRulePreviewAction: vi.fn() }));
function fixture() { const source = groupSourceFixture(ruleReadyTask()); return groupRuleFixture(groupFactFixture(source, groupRecordFixture(source))); }
it("shows known, unknown and unprocessed evidence without approval controls", () => {
  render(<GroupRulePreview taskId="task" prepId="prep" initialResult={{ ok: true, value: fixture() }} />);
  expect(screen.getAllByRole("article")).toHaveLength(3);
  expect(screen.getByText("事实未知，不能形成资格规则")).toBeVisible();
  expect(screen.getByText("待处理：字段或证据尚不能用于规则")).toBeVisible();
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /批准|保存|提交/ })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "返回组字段审核" })).toHaveAttribute("href", "/review/investigations/task/group-facts/prep");
});
it.each(["stale", "forbidden", "unavailable"] as const)("hides old rows when reloading fails (%s)", async kind => {
  vi.mocked(loadGroupRulePreviewAction).mockResolvedValue({ ok: false, kind, error: "当前记录不可用" });
  render(<GroupRulePreview taskId="task" prepId="prep" initialResult={{ ok: true, value: fixture() }} />);
  fireEvent.click(screen.getByRole("button", { name: "重新读取当前预览" }));
  await waitFor(() => expect(screen.getByRole("alert")).toBeVisible());
  expect(screen.queryByRole("article")).not.toBeInTheDocument();
});
it("recovers explicitly after failure", async () => {
  vi.mocked(loadGroupRulePreviewAction).mockResolvedValue({ ok: true, value: fixture() });
  render(<GroupRulePreview taskId="task" prepId="prep" initialResult={{ ok: false, kind: "unavailable", error: "不可用" }} />);
  fireEvent.click(screen.getByRole("button", { name: "重新读取当前预览" }));
  await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(3));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
it("keeps an empty original group visible without inventing rules", () => {
  const value = fixture(); value.result.rows = [];
  render(<GroupRulePreview taskId="task" prepId="prep" initialResult={{ ok: true, value }} />);
  expect(screen.getByText("原组没有字段，没有可预览规则。")).toBeVisible();
});
it("dynamically reads the exact saved address", async () => {
  vi.mocked(loadGroupRulePreviewAction).mockResolvedValue({ ok: false, kind: "stale", error: "已过期" });
  render(await Page({ params: Promise.resolve({ taskId: "task", prepId: "prep" }) }));
  expect(dynamic).toBe("force-dynamic"); expect(loadGroupRulePreviewAction).toHaveBeenCalledWith("task", "prep");
  expect(screen.getByRole("alert")).toHaveTextContent("已过期");
});
