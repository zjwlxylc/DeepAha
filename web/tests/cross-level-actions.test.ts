import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, expect, it, vi } from "vitest";
import { loadCrossLevelAction } from "../app/review/investigations/cross-level-actions";
import { humanTestFetch, LocalHumanTestApiError } from "../lib/local-human-test";
import fixture from "./cross-level-fixture.json";
vi.mock("../lib/local-human-test", () => ({ humanTestFetch: vi.fn(), LocalHumanTestApiError: class extends Error { constructor(public status: number) { super(); } } }));
const task = fixture.dependencies.group.dependencies.group_source.source.task_id;
const plan = fixture.dependencies.group.snapshot.base_v2.plan_id;
const hash = (v: unknown) => createHash("sha256").update(JSON.stringify(v, (_k, x: unknown) => x && typeof x === "object" && !Array.isArray(x) ? Object.fromEntries(Object.entries(x).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : x)).digest("hex");
beforeEach(() => { vi.mocked(humanTestFetch).mockReset(); });
it("accepts the actual complete PostgreSQL response", async () => {
  vi.mocked(humanTestFetch).mockResolvedValue(fixture);
  expect(await loadCrossLevelAction(task, plan)).toEqual({ ok: true, value: fixture });
});
it("accepts a Python export with 1.0 after JSON parsing without rewriting frozen source hashes", async () => {
  const text = readFileSync(resolve(process.cwd(), "tests/cross-level-fixture.json"), "utf8");
  expect(text).toContain('"weight": 1.0');
  const parsed = JSON.parse(text);
  const before = parsed.dependencies_hash;
  vi.mocked(humanTestFetch).mockResolvedValue(parsed);
  expect(await loadCrossLevelAction(task, plan)).toEqual({ ok: true, value: parsed });
  expect(parsed.dependencies_hash).toBe(before);
});
it.each(["omit", "disposition", "pointer", "groups", "base", "target", "version", "qualification", "blocker"])("rejects rehashed %s projection", async change => {
  const v = structuredClone(fixture);
  if (change === "omit") v.snapshot.conditions.pop();
  if (change === "disposition") v.snapshot.conditions[0].disposition = "EXCLUDED";
  if (change === "pointer") v.snapshot.conditions[0].source_pointer = "/wrong";
  if (change === "groups") v.snapshot.semantic_review_groups = [];
  if (change === "base") v.dependencies.announcement.snapshot.base_v2.plan_id = task;
  if (change === "target") v.snapshot.target.unit_id = task;
  if (change === "version") v.snapshot.contract_version = "future";
  if (change === "qualification") v.snapshot.overall_qualification = "ELIGIBLE";
  if (change === "blocker") v.snapshot.blockers = [];
  v.dependencies_hash = hash(v.dependencies); v.snapshot_hash = hash(v.snapshot);
  vi.mocked(humanTestFetch).mockResolvedValue(v);
  expect(await loadCrossLevelAction(task, plan)).toMatchObject({ ok: false });
});
it.each([403, 409, 503])("hides HTTP %s failure", async status => {
  vi.mocked(humanTestFetch).mockRejectedValue(new LocalHumanTestApiError(status));
  expect(await loadCrossLevelAction(task, plan)).toMatchObject({ ok: false });
});
it("rejects invalid identity before calling the service", async () => {
  expect(await loadCrossLevelAction("../other", plan)).toMatchObject({ ok: false });
  expect(humanTestFetch).not.toHaveBeenCalled();
});
