"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { originalCondition } from "../../lib/cross-level";
import { decideRelation, loadRelation } from "../../app/review/investigations/relation-actions";
import { relationKinds, relationPath, relationStatus, type RelationDecision, type RelationResult, type RelationView } from "../../lib/relation-review";
export default function RelationReview({ task, plan, id, initial }: { task: string; plan: string; id: string; initial: RelationResult<RelationView> }) {
  const [result, setResult] = useState<RelationResult<RelationView> | null>(initial);
  const [reason, setReason] = useState(""), [choice, setChoice] = useState<RelationDecision["decision"]>("NEEDS_ADJUDICATION");
  const [busy, setBusy] = useState(false), [canRetry, setCanRetry] = useState(false);
  const active = useRef(false);
  const attempt = useRef<{ request: Parameters<typeof decideRelation>[2]; nonce: string } | null>(null);
  async function run(retry = false) {
    if (active.current) return;
    if (!retry) {
      if (!result?.ok || !reason.trim()) return;
      attempt.current = { nonce: crypto.randomUUID(), request: { proposal_id: id, expected_proposal_payload_hash: result.value.proposal_payload_sha256, previous_decision_id: result.value.review.latest?.decision_id ?? null, decision: choice, reason } };
    }
    if (!attempt.current) return;
    active.current = true; setBusy(true); setResult(null); setCanRetry(false);
    try {
      const next = await decideRelation(task, plan, attempt.current.request, attempt.current.nonce);
      setResult(next);
      if (next.ok) { attempt.current = null; setReason(""); } else setCanRetry(true);
    } catch { setCanRetry(true); setResult({ ok: false, error: "回执读取失败，旧内容已隐藏，可重试原请求。" }); }
    finally { active.current = false; setBusy(false); }
  }
  async function reload() {
    if (active.current) return;
    active.current = true; setBusy(true); setResult(null); setCanRetry(false);
    try { const next = await loadRelation(task, plan, id); setResult(next); if (next.ok) attempt.current = null; }
    catch { setResult({ ok: false, error: "读取失败，旧内容已隐藏。" }); }
    finally { setCanRetry(attempt.current !== null); active.current = false; setBusy(false); }
  }
  const v = result?.ok ? result.value : null;
  return <main id="main-content" className="page-shell human-test-shell investigation-shell">
    <nav className="breadcrumbs"><Link prefetch={false} href={relationPath(task, plan)}>返回关系提案列表</Link></nav>
    <h1>关系提案与独立审核</h1>
    <p className="fixture-notice">这里审核条件之间的解释关系，不是用户资格批准。资格仍待确认；提案生产者不能审核自己的提案。</p>
    <button className="button button-secondary" disabled={busy} onClick={() => void reload()}>重新读取当前状态</button>
    {busy ? <p role="status">正在核对…</p> : null}
    {result && !result.ok ? <section role="alert"><p>{result.error}</p>{canRetry ? <button disabled={busy} onClick={() => void run(true)}>重试原请求</button> : null}</section> : null}
    {v ? <>
      <section className="human-test-panel"><h2>{relationStatus[v.review.status]}</h2><p>{relationKinds[v.package.proposal.relation]}</p><p>{v.package.proposal.reason}</p></section>
      <section className="human-test-panel"><h2>本提案涉及的条件</h2>{v.package.proposal.condition_ids.map(id => {
        const p = v.package.proposal, row = p.source_review.snapshot.conditions.find(r => r.condition.condition_id === id);
        const raw = row ? originalCondition(p.source_review, row.condition) : undefined;
        return <article key={id}><h3>{raw?.field ?? row?.condition.field_name ?? "条件未定位"}</h3>
          <p>{row ? ({ UNIT: "岗位层", ANNOUNCEMENT: "公告层", EMPLOYER_GROUP: "组层" })[row.condition.scope] : "来源未定位"}</p>
          <p>{typeof raw?.value === "string" ? raw.value : JSON.stringify(raw?.value ?? null)}</p>
          {p.displaced_condition_ids.includes(id) ? <p>此条件被提案指定为例外替代对象，尚不自动执行。</p> : null}
        </article>;
      })}</section>
      <section className="human-test-panel"><h2>提案引用的原文</h2>{v.package.proposal.evidence.map((e, i) => <article key={i}>
        <p>{e.purpose === "RELATION" ? "关系解释依据" : "条件依据"}</p><blockquote>{e.quote}</blockquote>
        {/^(https?):\/\//i.test(e.source_url) ? <a href={e.source_url} target="_blank" rel="noreferrer">打开来源原文</a> : null}
        <details><summary>查看完整证据定位</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(e.locator, null, 2)}</pre></details>
      </article>)}</section>
      <section className="human-test-panel"><h2>审核历史</h2>{v.package.decisions.length ? <ol>{v.package.decisions.map(d => <li key={d.decision_id}>
        <strong>{({ APPROVE: "审核通过", REJECT: "拒绝", NEEDS_ADJUDICATION: "需进一步裁决" })[d.decision]}</strong> · {d.created_at}<p>{d.reason}</p><small>审核账号：{d.reviewer_id}</small>
      </li>)}</ol> : <p>尚无独立审核记录。</p>}</section>
      {v.review.status !== "STALE" ? <form className="human-test-panel" onSubmit={e => { e.preventDefault(); void run(); }}>
        <h2>追加审核决定</h2><label>审核决定<select value={choice} disabled={busy} onChange={e => setChoice(e.target.value as RelationDecision["decision"])}>
          <option value="NEEDS_ADJUDICATION">需进一步裁决</option><option value="REJECT">拒绝提案</option><option value="APPROVE" disabled={v.package.proposal.relation === "UNRESOLVED"}>审核通过</option>
        </select></label><label>审核理由<textarea required maxLength={2000} value={reason} disabled={busy} onChange={e => setReason(e.target.value)} /></label>
        <button className="button button-primary" disabled={busy || !reason.trim()}>追加审核记录</button>
      </form> : <p role="status">当前依据已改变，不能继续审核这份旧提案。</p>}
    </> : null}
  </main>;
}
