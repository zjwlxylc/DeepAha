"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { loadGroupInheritanceAction } from "../../app/review/investigations/group-inheritance-actions";
import { inheritanceReasons, type GroupInheritanceResult } from "../../lib/group-inheritance";
import { groupApplicabilityPath } from "../../lib/group-applicability";
import { groupRecordPath } from "../../lib/group-sources";

export default function GroupInheritance({ taskId, planId, initialResult }: { taskId: string; planId: string; initialResult: GroupInheritanceResult }) {
  const [result, setResult] = useState<GroupInheritanceResult | null>(initialResult), [busy, setBusy] = useState(false);
  const active = useRef(false);
  async function reload() {
    if (active.current) return;
    active.current = true; setBusy(true); setResult(null);
    try { setResult(await loadGroupInheritanceAction(taskId, planId)); }
    catch { setResult({ ok: false, kind: "unavailable", error: "读取失败，旧内容已隐藏。" }); }
    finally { active.current = false; setBusy(false); }
  }
  const value = result?.ok ? result.value : null, group = value?.dependencies.group_source;
  return <main id="main-content" className="page-shell human-test-shell investigation-shell">
    <nav className="breadcrumbs" aria-label="面包屑"><Link href={`/review/investigations/${encodeURIComponent(taskId)}/unit-plans/${encodeURIComponent(planId)}`}>返回岗位条件快照</Link></nav>
    <h1>组条件对本岗位的范围预览</h1>
    <aside className="fixture-notice">本页只读，展示已审核的适用范围，不是资格结论。整体资格仍为 UNCERTAIN（待确认）。</aside>
    <button className="button button-secondary" disabled={busy} onClick={() => void reload()}>{busy ? "正在核对…" : "重新读取当前预览"}</button>
    {result && !result.ok ? <section className="human-test-panel" role="alert"><h2>当前预览不可用</h2><p>{result.error}</p></section> : null}
    {value && group ? <>
      <section className="human-test-panel"><h2>{group.registration?.group_identity.label ?? group.source.source_group.name ?? group.entity_id}</h2>
        <p>原组条件 {value.snapshot.group_conditions.length} 项 · 继承 {value.snapshot.group_conditions.filter(r => r.disposition === "INHERIT").length} · 不适用 {value.snapshot.group_conditions.filter(r => r.disposition === "EXCLUDE").length} · 待处理 {value.snapshot.group_conditions.filter(r => r.disposition === "UNRESOLVED").length}</p>
        <p>原组成员 {group.source.members.length} 个；本页只针对当前岗位。</p>
        {group.registration ? <Link href={groupRecordPath(taskId, group.registration.group_binding_id)}>查看完整组来源与成员</Link> : <p>组来源尚未登记，条件继续保留。</p>}
      </section>
      {!value.snapshot.group_conditions.length ? <p className="human-test-panel">冻结原组没有组级条件。这不表示岗位没有其他条件或已经符合资格。</p> : null}
      {value.snapshot.group_conditions.map(row => {
        const original = group.rule_preview?.result.fact_review.result.rows.find(r => r.source_index === row.condition.source_index);
        const sourceFacts = group.source.source_group.unit_level as { field: string; value: unknown; note?: string; evidence?: { quote: string; artifact_id: string; locator: unknown }[] }[];
        const raw = sourceFacts?.[value.snapshot.group_conditions.indexOf(row)];
        return <article className="human-test-panel group-fact-row" key={row.condition.condition_id}>
          <div><h2>{original?.original_field ?? raw?.field ?? row.condition.field_name}</h2><p>原始候选：{String(original?.raw_value ?? raw?.value ?? "未披露")}</p>
            {raw?.note ? <p>原备注：{raw.note}</p> : null}
            {(original?.evidence.map(e => e.reference) ?? raw?.evidence ?? []).map((e, i) => <div key={i}><blockquote>{e.quote}</blockquote>
              <Link href={`/review/investigations/${encodeURIComponent(taskId)}/materials/${encodeURIComponent(e.artifact_id)}`}>下载原件 · {e.artifact_id}</Link>
              <details><summary>查看原证据定位</summary><pre className="investigation-json">{JSON.stringify(e.locator, null, 2)}</pre></details>
            </div>)}
          </div><div><h3>{({ INHERIT: "继承范围", EXCLUDE: "明确不适用", UNRESOLVED: "仍待处理" })[row.disposition]}</h3>
            <p>{inheritanceReasons[row.reason] ?? "状态需要复核"}</p>
            {row.applicability ? <><p>审核理由：{row.applicability.request.reason}</p>{row.applicability.evidence_snapshot.map((e, i) => <blockquote key={i}>{e.quote}</blockquote>)}</> : null}
            {row.approval?.decision === "APPROVE" && row.source_rule?.rule_candidate_id && group.rule_review ? <Link href={groupApplicabilityPath({ task_id: taskId, target_plan_id: planId, source_rule_preparation_id: group.rule_review.preparation_id, source_rule_candidate_id: row.source_rule.rule_candidate_id })}>查看本条适用依据与决定历史</Link> : null}
          </div>
        </article>;
      })}
      <details className="human-test-panel"><summary>查看版本与审计摘要</summary><pre className="investigation-json">{JSON.stringify({ base_plan: planId, base_hash: value.snapshot.base_v2.plan_hash, dependencies_hash: value.dependencies_hash, snapshot_hash: value.snapshot_hash, contract: value.snapshot.contract_version }, null, 2)}</pre></details>
    </> : null}
  </main>;
}
