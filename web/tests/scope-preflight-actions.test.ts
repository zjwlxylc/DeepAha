import { expect, it, vi } from "vitest";
import { loadScopePreflight } from "../app/review/investigations/scope-actions";
import { humanTestFetch, LocalHumanTestApiError } from "../lib/local-human-test";
import f from "./scope-preflight-fixture.json";
vi.mock("../lib/local-human-test", () => ({ humanTestFetch: vi.fn(), LocalHumanTestApiError: class extends Error { constructor(public status: number) { super(); } } }));
it("accepts current and stale actual synthetic API exports", async () => {
  for (const v of [f.current, f.stale]) {
    vi.mocked(humanTestFetch).mockResolvedValue(v);
    expect(await loadScopePreflight(v.task_id, v.target_plan_id)).toEqual({ ok: true, value: v });
  }
});
it.each(["target", "safety", "version", "count", "duplicate", "pair", "time", "unknown-state", "missing-blocker", "inconsistent-time"])("refuses invalid %s", async attack => {
  const v = structuredClone(f.current);
  if (attack === "target") v.target_plan_id = v.task_id;
  if (attack === "safety") v.executable = true;
  if (attack === "version") v.contract_version = "future";
  if (attack === "count") v.source_row_count++;
  if (attack === "duplicate") v.conditions[1] = v.conditions[0];
  if (attack === "pair") Object.assign(v, { uncovered_condition_pairs: [["foreign", "foreign"]] });
  if (attack === "time") v.as_of = "invalid";
  if (attack === "unknown-state") v.local_evidence_validity[0].status = "VERIFIED_FOREVER";
  if (attack === "inconsistent-time") v.local_evidence_validity[0].status = "EXPIRED";
  if (attack === "missing-blocker") v.blockers = [];
  vi.mocked(humanTestFetch).mockResolvedValue(v);
  expect((await loadScopePreflight(f.current.task_id, f.current.target_plan_id)).ok).toBe(false);
});

it.each([401, 403, 404, 409, 500])("returns recoverable failure for HTTP %s", async status => {
  vi.mocked(humanTestFetch).mockRejectedValue(new LocalHumanTestApiError(status));
  const result = await loadScopePreflight(f.current.task_id, f.current.target_plan_id);
  expect(result.ok).toBe(false);
  if (!result.ok) expect(result.error).toContain("旧结果已隐藏");
});
