"use server";
import { createHash } from "node:crypto";
import { humanTestFetch, LocalHumanTestApiError } from "../../../lib/local-human-test";
import { crossLevelVersion, type CrossLevelReview, type CrossLevelResult } from "../../../lib/cross-level";
import { inheritanceVersion } from "../../../lib/group-inheritance";
import { announcementSnapshotAdapter, announcementSnapshotContract } from "../../../lib/announcement-snapshots";
import { canonicalJson as stable, codePointCompare } from "../../../lib/cross-level-canonical";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
function hash(v: unknown) { return createHash("sha256").update(stable(v)).digest("hex"); }
export async function loadCrossLevelAction(task: string, plan: string): Promise<CrossLevelResult> {
  try {
    if (![task, plan].every(v => uuid.test(v))) throw new Error("Invalid identity");
    // Only the authenticated online service supplies inputs. This is not offline replay
    // and does not accept a browser-provided dependency hash as an approval anchor.
    const v = await humanTestFetch<CrossLevelReview>(`/investigations/${task}/unit-plans/${plan}/cross-level-preview`);
    const d = v.dependencies, s = v.snapshot, g = d.group, a = d.announcement, base = g.snapshot.base_v2;
    // The backend verifies frozen input hashes before serialization. response.json()
    // loses numeric spelling (1.0 -> 1), so never re-hash raw sources in JavaScript.
    // This snapshot contains only schema-defined integers/strings/bools; its complete
    // projection is independently rebuilt below from the authenticated response.
    if (![v.dependencies_hash, v.snapshot_hash, s.base_v2_hash, g.dependencies_hash,
      g.snapshot_hash, a.dependencies_hash, base.plan_hash, base.context_hash].every(h => /^[0-9a-f]{64}$/.test(h))) throw new Error("Invalid digest reference");
    if (d.contract_version !== crossLevelVersion || s.contract_version !== crossLevelVersion
      || s.scope !== "CROSS_LEVEL_REVIEW_ONLY" || s.executable !== false || s.overall_qualification !== "UNCERTAIN"
      || hash(s) !== v.snapshot_hash || s.base_v2_hash !== a.dependencies.base_v2_hash
      || stable(base) !== stable(a.snapshot.base_v2) || stable(base) !== stable(g.dependencies.base_v2)
      || stable(s.target) !== stable(base.plan.target) || base.plan_id !== plan || base.plan.qualification_plan_id !== plan
      || base.plan_hash !== a.dependencies.base_plan_hash || base.context_hash !== a.dependencies.base_context_hash
      || g.dependencies.group_source.source.task_id !== task
      || g.dependencies.contract_version !== inheritanceVersion || g.snapshot.contract_version !== inheritanceVersion
      || a.dependencies.contract_version !== announcementSnapshotContract || a.snapshot.contract_version !== announcementSnapshotContract
      || a.dependencies.adapter_version !== announcementSnapshotAdapter || a.snapshot.adapter_version !== announcementSnapshotAdapter
      || g.snapshot.overall_qualification !== "UNCERTAIN" || a.snapshot.overall_qualification !== "UNCERTAIN") throw new Error("Invalid source identity or version");
    const manifest = base.plan.manifest.conditions;
    if (stable(a.snapshot.announcement_conditions.map(r => r.condition)) !== stable(manifest.filter(c => c.scope === "ANNOUNCEMENT"))
      || stable(g.snapshot.group_conditions.map(r => r.condition)) !== stable(manifest.filter(c => c.scope === "EMPLOYER_GROUP"))) throw new Error("Invalid denominator");
    const expected = manifest.map((condition, index) => {
      let disposition: string = "LOCAL", source_pointer = `/dependencies/group/snapshot/base_v2/plan/manifest/conditions/${index}`;
      if (condition.scope === "ANNOUNCEMENT") {
        const i = a.snapshot.announcement_conditions.findIndex(r => r.condition.condition_id === condition.condition_id);
        disposition = a.snapshot.announcement_conditions[i].disposition;
        source_pointer = `/dependencies/announcement/snapshot/announcement_conditions/${i}`;
      } else if (condition.scope === "EMPLOYER_GROUP") {
        const i = g.snapshot.group_conditions.findIndex(r => r.condition.condition_id === condition.condition_id);
        disposition = ({ INHERIT: "INHERITED", EXCLUDE: "EXCLUDED", UNRESOLVED: "UNRESOLVED" })[g.snapshot.group_conditions[i].disposition];
        source_pointer = `/dependencies/group/snapshot/group_conditions/${i}`;
      } else if (condition.scope !== "UNIT") throw new Error("Unknown scope");
      return { condition, disposition, source_pointer };
    });
    const groups = [...new Set(expected.map(r => r.condition.field_name))].sort(codePointCompare).flatMap(field => {
      const members = expected.filter(r => r.condition.field_name === field);
      return new Set(members.map(r => r.condition.scope)).size > 1 ? [{ field_name: field,
        condition_ids: members.map(r => r.condition.condition_id), excluded_condition_ids: members.filter(r => r.disposition === "EXCLUDED").map(r => r.condition.condition_id), relation: "NOT_EVALUATED" }] : [];
    });
    const blockers = [...new Set([...base.plan.manifest.upstream_blockers, "CROSS_LEVEL_SEMANTICS_NOT_REVIEWED"])].sort(codePointCompare);
    if (stable(s.conditions) !== stable(expected) || stable(s.semantic_review_groups) !== stable(groups)
      || stable(s.blockers) !== stable(blockers)) throw new Error("Invalid full projection");
    return { ok: true, value: v };
  } catch (error) {
    const status = error instanceof LocalHumanTestApiError ? error.status : 0;
    return { ok: false, kind: [401, 403].includes(status) ? "forbidden" : [404, 409].includes(status) ? "stale" : "unavailable",
      error: "未取得有效的当前跨层级预览，旧内容已隐藏。请核对权限或重新读取。" };
  }
}
