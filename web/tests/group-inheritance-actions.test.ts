import { createHash } from "node:crypto";
import { beforeEach, expect, it, vi } from "vitest";
import { loadGroupInheritanceAction } from "../app/review/investigations/group-inheritance-actions";
import { humanTestFetch, LocalHumanTestApiError } from "../lib/local-human-test";
import fixture from "./group-inheritance-fixture.json";
import type { GroupInheritance } from "../lib/group-inheritance";
vi.mock("../lib/local-human-test", () => ({ humanTestFetch: vi.fn(), LocalHumanTestApiError: class extends Error { constructor(public status: number) { super(); } } }));
const task = fixture.dependencies.group_source.source.task_id, plan = fixture.snapshot.base_v2.plan_id;
const hash = (v: unknown) => createHash("sha256").update(JSON.stringify(v, (_k, x: unknown) => x && typeof x === "object" && !Array.isArray(x) ? Object.fromEntries(Object.entries(x).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : x)).digest("hex");
beforeEach(() => { vi.mocked(humanTestFetch).mockReset(); });
it("accepts an actual PostgreSQL projection without modifying it", async () => {
  vi.mocked(humanTestFetch).mockResolvedValue(fixture);
  expect(await loadGroupInheritanceAction(task, plan)).toEqual({ ok: true, value: fixture });
});
it.each(["omit", "exclude", "base", "history", "qualification", "identity", "raw", "empty"])("rejects rehashed %s corruption", async change => {
  const v = structuredClone(fixture);
  if (change === "omit") v.snapshot.group_conditions.pop();
  if (change === "exclude") v.snapshot.group_conditions[1].disposition = "EXCLUDE";
  if (change === "base") v.snapshot.base_v2.context.check_id = task;
  if (change === "qualification") v.snapshot.overall_qualification = "ELIGIBLE";
  if (change === "identity") v.dependencies.group_source.source.task_id = plan;
  if (change === "raw") v.dependencies.group_source.rule_preview.result.fact_review.result.rows[1].raw_value = "伪造条件";
  if (change === "empty") {
    for (const base of [v.dependencies.base_v2, v.snapshot.base_v2]) {
      base.plan.manifest.conditions = base.plan.manifest.conditions.filter(c => c.scope !== "EMPLOYER_GROUP");
      base.plan_hash = hash(base.plan);
    }
    v.snapshot.group_conditions = [];
  }
  if (change === "history") { const key = Object.keys(v.dependencies.group_source.applicability_histories)[0] as keyof typeof v.dependencies.group_source.applicability_histories; v.dependencies.group_source.applicability_histories[key] = []; }
  v.dependencies_hash = hash(v.dependencies); v.snapshot_hash = hash(v.snapshot);
  vi.mocked(humanTestFetch).mockResolvedValue(v);
  expect(await loadGroupInheritanceAction(task, plan)).toMatchObject({ ok: false });
});
it.each([403, 409, 503])("hides HTTP %s responses", async status => {
  vi.mocked(humanTestFetch).mockRejectedValue(new LocalHumanTestApiError(status));
  expect(await loadGroupInheritanceAction(task, plan)).toMatchObject({ ok: false });
});
it.each(["missing_group_fields", "missing_evidence", "legacy_note", "missing_locator"])("accepts optional %s", async shape => {
  const v = structuredClone(fixture) as GroupInheritance;
  const g = v.dependencies.group_source;
  if (shape === "missing_group_fields") {
    delete g.source.source_group.unit_level;
    g.rule_preview = null; g.rule_review = null; g.applicability_histories = {};
    for (const base of [v.dependencies.base_v2, v.snapshot.base_v2]) {
      base.plan.manifest.conditions = base.plan.manifest.conditions.filter(c => c.scope !== "EMPLOYER_GROUP"); base.plan_hash = hash(base.plan);
    }
    v.snapshot.group_conditions = [];
  } else {
    const raw = (g.source.source_group.unit_level as { evidence?: { locator?: unknown }[]; note?: string }[])[1];
    const row = g.rule_preview!.result.fact_review.result.rows[1];
    if (shape === "missing_evidence") { delete raw.evidence; row.original.evidence = []; row.evidence = []; }
    else if (shape === "legacy_note") { raw.note = "Historical note"; delete row.original.note; }
    else { delete raw.evidence![0].locator; row.original.evidence[0].locator = {}; row.evidence[0].reference.locator = {}; }
  }
  v.dependencies_hash = hash(v.dependencies); v.snapshot_hash = hash(v.snapshot);
  vi.mocked(humanTestFetch).mockResolvedValue(v);
  expect(await loadGroupInheritanceAction(task, plan)).toMatchObject({ ok: true });
});
