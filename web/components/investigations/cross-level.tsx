"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { loadCrossLevelAction } from "../../app/review/investigations/cross-level-actions";
import { originalCondition, type CrossLevelResult } from "../../lib/cross-level";
import { groupInheritancePath, inheritanceReasons } from "../../lib/group-inheritance";
import { announcementPreviewPath, announcementReasons } from "../../lib/announcement-snapshots";

const scopes = { UNIT: "岗位层", ANNOUNCEMENT: "公告层", EMPLOYER_GROUP: "组层" };
const dispositions = { LOCAL: "岗位层条件", INHERITED: "继承范围", EXCLUDED: "明确不适用", UNRESOLVED: "待处理" };
const states: Record<string, string> = { KNOWN: "有原文依据", UNKNOWN: "调查后信息不足", UNPROCESSED: "尚未处理", CONFLICT: "原条件有冲突", UNSUPPORTED: "字段暂不支持", REJECTED: "候选被拒绝", UNLOCATED: "证据尚未定位" };
export default function CrossLevel({ taskId, planId, initialResult }: { taskId: string; planId: string; initialResult: CrossLevelResult }) {
  const [result, setResult] = useState<CrossLevelResult | null>(initialResult), [busy, setBusy] = useState(false);
  const active = useRef(false);
  async function reload() {
    if (active.current) return;
    active.current = true; setBusy(true); setResult(null);
    try { setResult(await loadCrossLevelAction(taskId, planId)); }
    catch { setResult({ ok: false, kind: "unavailable", error: "读取失败，旧内容已隐藏。" }); }
    finally { active.current = false; setBusy(false); }
  }
  const value = result?.ok ? result.value : null;
  const back = `/review/investigations/${encodeURIComponent(taskId)}/unit-plans/${encodeURIComponent(planId)}`;
  return <main id="main-content" className="page-shell human-test-shell investigation-shell">
    <nav className="breadcrumbs" aria-label="面包屑"><Link prefetch={false} href={back}>返回岗位条件快照</Link></nav>
    <h1>公告、组与岗位条件总览</h1>
    <aside className="fixture-notice">本页只读，展示条件来源与适用范围，不是资格结论。整体资格仍为 UNCERTAIN（待确认），不能据此自动裁决。</aside>
    <button className="button button-secondary" disabled={busy} onClick={() => void reload()}>{busy ? "正在核对…" : "重新读取当前预览"}</button>
    {result && !result.ok ? <section className="human-test-panel" role="alert"><h2>当前预览不可用</h2><p>{result.error}</p></section> : null}
    {value ? <>
      <section className="human-test-panel"><h2>完整条件范围</h2>
        <p>全部条件 {value.snapshot.conditions.length} 项 · 岗位层 {value.snapshot.conditions.filter(r => r.disposition === "LOCAL").length} · 继承范围 {value.snapshot.conditions.filter(r => r.disposition === "INHERITED").length} · 明确不适用 {value.snapshot.conditions.filter(r => r.disposition === "EXCLUDED").length} · 待处理 {value.snapshot.conditions.filter(r => r.disposition === "UNRESOLVED").length}</p>
        <p>岗位层表示条件来源，不表示已经符合。排除一条条件不会排除同字段的其他条件。</p>
      </section>
      <section className="human-test-panel"><h2>同字段跨层级关系</h2>
        <p>以下仅为审核索引，未判断累积、例外或冲突；没有列出的不同字段之间也可能有关联。</p>
        {value.snapshot.semantic_review_groups.length ? <ul>{value.snapshot.semantic_review_groups.map(g => <li key={g.field_name}>
          <strong>{originalCondition(value, value.snapshot.conditions.find(r => r.condition.condition_id === g.condition_ids[0])!.condition)?.field ?? g.field_name}</strong> · {g.condition_ids.length} 条 · 含明确不适用 {g.excluded_condition_ids.length} 条
          <ul>{g.condition_ids.map(id => { const row = value.snapshot.conditions.find(r => r.condition.condition_id === id)!;
            return <li key={id}><a href={`#condition-${encodeURIComponent(id)}`}>{scopes[row.condition.scope]} · {dispositions[row.disposition]}</a></li>; })}</ul>
        </li>)}</ul> : <p>未发现跨层级同名字段。这不代表没有例外或冲突。</p>}
      </section>
      {value.snapshot.conditions.map(row => {
        const c = row.condition, raw = originalCondition(value, c);
        const ann = value.dependencies.announcement.snapshot.announcement_conditions.find(r => r.condition.condition_id === c.condition_id);
        const group = value.dependencies.group.snapshot.group_conditions.find(r => r.condition.condition_id === c.condition_id);
        const reasons = ann?.reasons.map(r => announcementReasons[r] ?? r) ?? (group ? [inheritanceReasons[group.reason] ?? group.reason] : []);
        const receipt = ann?.applicability ?? group?.applicability;
        const sourcePath = c.scope === "ANNOUNCEMENT" ? announcementPreviewPath({ task_id: taskId, base_plan_id: planId }) : c.scope === "EMPLOYER_GROUP" ? groupInheritancePath(taskId, planId) : back;
        return <article id={`condition-${c.condition_id}`} className="human-test-panel group-fact-row" key={c.condition_id}>
          <div><p>{scopes[c.scope]} · 基础快照状态：{states[c.state] ?? c.state}</p><h2>{raw?.field ?? c.field_name}</h2>
            <p>原始条件：{raw?.value == null ? "未披露" : String(raw.value)}</p>
            {raw?.note ? <p>原备注：{raw.note}</p> : null}
            {(raw?.evidence ?? []).map((e, i) => <div key={i}><blockquote>{e.quote}</blockquote>
              <Link prefetch={false} href={`/review/investigations/${encodeURIComponent(taskId)}/materials/${encodeURIComponent(e.artifact_id)}`}>下载原件 · {e.artifact_id}</Link>
              <details><summary>查看原证据定位</summary><pre className="investigation-json">{JSON.stringify(e.locator ?? {}, null, 2)}</pre></details>
            </div>)}
            {!raw?.evidence?.length ? <p>此条件没有可展示的原文引用，仍需核对。</p> : null}
          </div><div><h3>{dispositions[row.disposition]}</h3>
            {reasons.map((reason, i) => <p key={i}>{reason}</p>)}
            {receipt ? <><p>范围审核理由：{receipt.request.reason}</p>{receipt.evidence_snapshot.map((e, i) => <blockquote key={i}>{e.quote}</blockquote>)}</> : null}
            <Link prefetch={false} href={sourcePath}>查看{scopes[c.scope]}完整条件与审核依据</Link>
          </div>
        </article>;
      })}
      <details className="human-test-panel"><summary>查看版本与待审标记</summary><pre className="investigation-json">{JSON.stringify({ contract: value.snapshot.contract_version, base_plan: planId, dependencies_hash: value.dependencies_hash, snapshot_hash: value.snapshot_hash, blockers: value.snapshot.blockers }, null, 2)}</pre></details>
    </> : null}
  </main>;
}
