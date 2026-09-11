import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import ScopePreflight from "../components/investigations/scope-preflight";
import { loadScopePreflight } from "../app/review/investigations/scope-actions";
import type { ScopePreflightView } from "../lib/scope-preflight";
import f from "./scope-preflight-fixture.json";
vi.mock("../app/review/investigations/scope-actions", () => ({ loadScopePreflight: vi.fn() }));
const v = f.current as ScopePreflightView;
it("shows all conditions, missing boundaries and exact review links without claiming eligibility", () => {
  render(<ScopePreflight task={v.task_id} plan={v.target_plan_id} initial={{ ok: true, value: v }} />);
  expect(screen.getByRole("heading", { name: "条件范围预检" })).toBeVisible();
  expect(screen.getAllByRole("link", { name: "查看条件原文与依据" })).toHaveLength(v.conditions.length);
  expect(screen.getByText(/结束时间尚未建立，不能视为永久有效/)).toBeVisible();
  expect(screen.getByRole("link", { name: "关系提案 1" })).toHaveAttribute("href", expect.stringContaining(`?proposal=${v.relations[0].proposal_id}`));
  expect(screen.getByText(/整体资格仍待确认/)).toBeVisible();
});
it("clears old results while loading, hides them on failure and supports recovery", async () => {
  let release!: (v: Awaited<ReturnType<typeof loadScopePreflight>>) => void;
  vi.mocked(loadScopePreflight).mockImplementationOnce(() => new Promise(resolve => { release = resolve; }));
  render(<ScopePreflight task={v.task_id} plan={v.target_plan_id} initial={{ ok: true, value: v }} />);
  fireEvent.click(screen.getByRole("button", { name: "重新读取预检" }));
  expect(screen.getByRole("status")).toBeVisible();
  expect(screen.queryByRole("link", { name: "关系提案 1" })).not.toBeInTheDocument();
  await act(async () => release({ ok: false, error: "会话已失效" }));
  expect(screen.getByRole("alert")).toHaveTextContent("会话已失效");
  vi.mocked(loadScopePreflight).mockResolvedValue({ ok: true, value: f.stale as ScopePreflightView });
  fireEvent.click(screen.getByRole("button", { name: "重新读取预检" }));
  expect(await screen.findAllByText("依据已变化，旧决定失效")).toHaveLength(2);
});

it("empty sections keep uncertainty instead of presenting a passed check", () => {
  const empty = structuredClone(v);
  Object.assign(empty, { source_row_count: 0, conditions: [], excluded_source_rows: [], relations: [], local_evidence_validity: [], local_kernel_blockers: [] });
  render(<ScopePreflight task={v.task_id} plan={v.target_plan_id} initial={{ ok: true, value: empty }} />);
  expect(screen.getByText(/尚无登记条件/)).toBeVisible();
  expect(screen.getByText(/尚无关系提案/)).toBeVisible();
  expect(screen.getByText(/尚无可展示的岗位证据时间记录/)).toBeVisible();
  expect(screen.getByText(/整体资格仍待确认/)).toBeVisible();
});
