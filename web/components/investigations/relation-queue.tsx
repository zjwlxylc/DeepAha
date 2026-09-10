"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { loadRelationQueue } from "../../app/review/investigations/queue-actions";
import { crossLevelPath } from "../../lib/cross-level";
import { relationKinds, relationPath, relationStatus, type RelationResult } from "../../lib/relation-review";
import type { RelationQueueView } from "../../lib/relation-queue";
export default function RelationQueue({ task, plan, initial }: { task: string; plan: string; initial: RelationResult<RelationQueueView> }) {
  const [result, setResult] = useState<RelationResult<RelationQueueView> | null>(initial);
  const [busy, setBusy] = useState(false), [filter, setFilter] = useState("ALL"), [after, setAfter] = useState<string>();
  const active = useRef(false);
  async function read(cursor?: string) {
    if (active.current) return;
    active.current = true; setBusy(true); setAfter(cursor); setResult(null);
    try { setResult(await loadRelationQueue(task, plan, cursor)); }
    catch { setResult({ ok: false, error: "当前读取失败，旧状态已隐藏。" }); }
    finally { active.current = false; setBusy(false); }
  }
  const v = result?.ok ? result.value : null;
  const shown = v?.proposals.filter(p => filter === "ALL" || p.status === filter) ?? [];
  return <main id="main-content" className="page-shell human-test-shell investigation-shell">
    <nav className="breadcrumbs"><Link prefetch={false} href={crossLevelPath(task, plan)}>返回跨层级条件总览</Link></nav>
    <h1>关系提案审核队列</h1>
    <aside className="fixture-notice">状态仅代表本次读取时的关系审核结果，进入详情时会再次核对。提案审核不等于资格通过，整体资格仍为 UNCERTAIN（待确认）。</aside>
    <div className="human-test-actions"><Link className="button button-primary" prefetch={false} href={`${relationPath(task, plan)}/new`}>新建关系提案</Link>
      <button className="button button-secondary" disabled={busy} onClick={() => void read(after)}>重新读取本页</button>
      {after ? <button className="button button-secondary" disabled={busy} onClick={() => void read()}>返回第一页</button> : null}</div>
    {busy ? <p role="status">正在核对当前来源与审核历史…</p> : null}
    {result && !result.ok ? <p role="alert">{result.error}</p> : null}
    {v ? <><p>本次读取时间：{v.read_at} · 本页 {v.proposals.length} 份提案</p>
      <div className="review-form"><label>筛选本页审核状态<select value={filter} onChange={e => setFilter(e.target.value)}><option value="ALL">全部状态</option>{Object.entries(relationStatus).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label></div>
      <p>筛选仅作用于当前页，不代表该岗位的全部待办。来源变化后，历史批准会失效。</p>
      {shown.map(p => <article className="human-test-panel" key={p.proposal_id}>
        <h2><Link prefetch={false} href={relationPath(task, plan, p.proposal_id)}>关系提案 {v.proposals.indexOf(p) + 1}</Link> · {relationKinds[p.relation]}</h2>
        <p><strong>{relationStatus[p.status]}</strong></p>
        {p.is_own_proposal ? <p>自己创建，需他人独立审核</p> : null}
        <p>{p.reason}</p><p>所选条件：{p.condition_ids.join("、")}</p><p>创建于 {p.created_at}</p>
      </article>)}
      {!shown.length ? <p>{v.proposals.length ? "本页没有符合筛选条件的提案。" : "本页没有已保存提案。"}</p> : null}
      {v.next_after ? <button className="button button-secondary" disabled={busy} onClick={() => void read(v.next_after!)}>读取下一页</button> : null}
    </> : null}
  </main>;
}
