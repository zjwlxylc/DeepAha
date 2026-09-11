"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { loadScopePreflight } from "../../app/review/investigations/scope-actions";
import { crossLevelPath } from "../../lib/cross-level";
import { relationKinds, relationPath, relationStatus, type RelationResult } from "../../lib/relation-review";
import { scopeDispositions, scopeIssues, scopeLabels, timeLabels, type ScopePreflightView } from "../../lib/scope-preflight";
const fields: Record<string, string> = { education_requirements: "学历要求", age_requirements: "年龄要求", major_requirements: "专业要求", graduation_requirements: "毕业身份要求" };
const date = (value: string) => new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
export default function ScopePreflight({ task, plan, initial }: { task: string; plan: string; initial: RelationResult<ScopePreflightView> }) {
  const [result, setResult] = useState<RelationResult<ScopePreflightView> | null>(initial);
  const [busy, setBusy] = useState(false), active = useRef(false);
  async function reload() {
    if (active.current) return;
    active.current = true; setBusy(true); setResult(null);
    try { setResult(await loadScopePreflight(task, plan)); }
    catch { setResult({ ok: false, error: "读取失败，旧结果已隐藏。请重新读取。" }); }
    finally { active.current = false; setBusy(false); }
  }
  const v = result?.ok ? result.value : null;
  const back = `/review/investigations/${encodeURIComponent(task)}/unit-plans/${encodeURIComponent(plan)}`;
  const label = (id: string) => { const c = v?.conditions.find(c => c.condition_id === id); return c ? `${scopeLabels[c.scope]} · ${fields[c.field_name] ?? c.field_name}` : "历史条件"; };
  const conditionLink = (id: string) => `${crossLevelPath(task, plan)}#condition-${encodeURIComponent(id)}`;
  const proposalLink = (id: string) => <Link prefetch={false} href={relationPath(task, plan, id)}>关系提案 {(v?.relations.findIndex(r => r.proposal_id === id) ?? -1) + 1}</Link>;
  return <main id="main-content" className="page-shell human-test-shell investigation-shell">
    <nav className="breadcrumbs" aria-label="面包屑"><Link prefetch={false} href={back}>返回岗位条件快照</Link></nav>
    <h1>条件范围预检</h1>
    <aside className="fixture-notice">本页只读，帮助定位待处理项。整体资格仍待确认，预检不能替代完整范围的独立审核，也不能据此作出资格裁决。</aside>
    <div className="card-actions"><button className="button button-secondary" disabled={busy} onClick={() => void reload()}>重新读取预检</button>
      <Link className="button button-secondary" prefetch={false} href={crossLevelPath(task, plan)}>查看全部条件原文</Link>
      <Link className="button button-secondary" prefetch={false} href={relationPath(task, plan)}>进入关系审核队列</Link></div>
    {busy ? <p role="status">正在核对当前条件与审核记录…</p> : null}
    {result && !result.ok ? <section className="human-test-panel" role="alert"><h2>预检暂不可用</h2><p>{result.error}</p></section> : null}
    {v ? <>
      <p>核对时间：{date(v.as_of)}（北京时间）</p>
      <section className="human-test-panel"><h2>仍需完成的核对</h2>
        <ul>{v.blockers.filter(code => scopeIssues[code]).map(code => <li key={code}>{scopeIssues[code]}</li>)}</ul>
        {v.blockers.some(code => !scopeIssues[code]) ? <p>另有 {v.blockers.filter(code => !scopeIssues[code]).length} 项来源限制，<Link prefetch={false} href={back}>返回岗位快照核对</Link>。</p> : null}
      </section>
      <section className="human-test-panel"><h2>条件与原件缺口</h2>
        <p>登记来源 {v.source_row_count} 行 · 本岗位范围 {v.conditions.length} 条 · 其他目标排除 {v.excluded_source_rows.length} 行</p>
        <p>登记行齐全不等于官方原件已发现齐全。未核验证据引用 {v.unresolved_source_references.length} 条；<Link prefetch={false} href={`/review/investigations/${encodeURIComponent(task)}`}>返回调查任务核对原件</Link>。</p>
        {!v.conditions.length ? <p>尚无登记条件，这不代表没有条件或已经核验完整。</p> : null}
        {v.conditions.map(c => <article className="human-test-panel" key={c.condition_id}>
          <h3>{label(c.condition_id)}</h3><p>{scopeDispositions[c.disposition]}</p>
          {c.issues.length ? <ul>{c.issues.map((issue, i) => <li key={i}>{scopeIssues[issue] ?? "此条件仍有待核对事项"}</li>)}</ul> : <p>本次未列出该条件的单项缺口，不代表完整范围审核通过。</p>}
          {v.source_notes.filter(n => n.condition_id === c.condition_id).map((n, i) => <p key={i}>原备注：{n.note}</p>)}
          <Link prefetch={false} href={conditionLink(c.condition_id)}>查看条件原文与依据</Link>
        </article>)}
      </section>
      <section className="human-test-panel"><h2>关系审阅缺口</h2>
        <p>以下只核对同字段的跨层条件对；未列出缺口不证明不存在其他条件联动。</p>
        {v.uncovered_condition_pairs.length ? <ul>{v.uncovered_condition_pairs.map((pair, i) => <li key={i}>{pair.map((id, j) => <span key={id}>{j ? " 与 " : ""}<Link prefetch={false} href={conditionLink(id)}>{label(id)}</Link></span>)}：缺少当前有效的关系审阅</li>)}</ul> : <p>本次未列出未覆盖的同字段条件对，仍需完整范围审核。</p>}
        {v.overlapping_relation_pairs.length ? <><h3>交叠关系需要共同核对</h3><ul>{v.overlapping_relation_pairs.map((pair, i) => <li key={i}>{proposalLink(pair[0])} 与 {proposalLink(pair[1])}</li>)}</ul></> : null}
        {!v.relations.length ? <p>尚无关系提案，不能据此认定没有冲突或例外。</p> : <ul>{v.relations.map(r => <li key={r.proposal_id}>{proposalLink(r.proposal_id)} · {relationKinds[r.relation]}<p>{relationStatus[r.status]}</p></li>)}</ul>}
      </section>
      <section className="human-test-panel"><h2>证据有效期</h2>
        <p>这里只展示已有岗位证据的记录区间；公告和组级继承条件的有效期仍待独立审核。</p>
        {!v.local_evidence_validity.length ? <p>尚无可展示的岗位证据时间记录，不代表已通过有效期核验。</p> : <ul>{v.local_evidence_validity.map((e, i) => <li key={`${e.rule_id}:${e.evidence_ref_id}`}><strong>岗位证据 {i + 1}：{timeLabels[e.status]}</strong>
          <p>{date(e.valid_from)} 起，{e.valid_until ? `${date(e.valid_until)} 止（结束时刻不包含）` : "结束时间未建立"}（北京时间）</p>
          <Link prefetch={false} href={back}>查看岗位规则与证据</Link></li>)}</ul>}
        <p>原生岗位计划另保留 {v.local_kernel_blockers.length} 项规则限制。这不是继承、例外处理后的最终执行结果。</p>
      </section>
    </> : null}
  </main>;
}
