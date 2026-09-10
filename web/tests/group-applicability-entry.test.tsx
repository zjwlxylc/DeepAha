import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import Page from "../app/review/investigations/[taskId]/unit-plans/[planId]/page";
import { loadGroupApplicabilityEntries } from "../app/review/investigations/group-applicability-actions";
import { getInvestigation } from "../lib/investigations";
import { humanTestFetch } from "../lib/local-human-test";
import { unitSnapshotFixture } from "./investigations-fixture";
vi.mock("../app/review/investigations/group-applicability-actions", () => ({ loadGroupApplicabilityEntries: vi.fn() }));
vi.mock("../lib/investigations", () => ({ getInvestigation: vi.fn() }));
vi.mock("../lib/local-human-test", () => ({ humanTestFetch: vi.fn(), LocalHumanTestApiError: class extends Error {} }));
beforeEach(() => { vi.clearAllMocks(); });
it.each(["forbidden", "stale", "unavailable"] as const)("hides first successful reads when later index is %s", async kind => {
  const { task, snapshot } = unitSnapshotFixture();
  vi.mocked(humanTestFetch).mockResolvedValue(snapshot);
  vi.mocked(getInvestigation).mockResolvedValue(task);
  vi.mocked(loadGroupApplicabilityEntries).mockResolvedValue({ ok: false, kind, error: "后续读取失败" });
  render(await Page({ params: Promise.resolve({ taskId: task.task_id, planId: snapshot.plan_id }) }));
  expect(screen.getByRole("alert")).toHaveTextContent("后续读取失败");
  expect(screen.queryByRole("heading", { name: "逐项条件与依据" })).not.toBeInTheDocument();
});
it("does not claim missing rules mean no group conditions", async () => {
  const { task, snapshot } = unitSnapshotFixture();
  vi.mocked(humanTestFetch).mockResolvedValue(snapshot);
  vi.mocked(getInvestigation).mockResolvedValue(task);
  vi.mocked(loadGroupApplicabilityEntries).mockResolvedValue({ ok: true, value: [] });
  render(await Page({ params: Promise.resolve({ taskId: task.task_id, planId: snapshot.plan_id }) }));
  expect(screen.getByText(/这不代表没有组条件/)).toBeVisible();
});
