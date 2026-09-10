"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { loadProposalContext, proposeRelation } from "../../app/review/investigations/proposal-actions";
import { crossLevelPath, originalCondition } from "../../lib/cross-level";
import { relationKinds, relationPath, type RelationResult } from "../../lib/relation-review";
import type { ProposalContext, ProposalRequest } from "../../lib/relation-proposal";
const scopes = { UNIT: "岗位层", ANNOUNCEMENT: "公告层", EMPLOYER_GROUP: "组层" };
export default function ProposalForm({ task, plan, initial }: { task: string; plan: string; initial: RelationResult<ProposalContext> }) {
  const router = useRouter(), active = useRef(false);
  const [result, setResult] = useState<RelationResult<ProposalContext> | null>(initial);
  const [busy, setBusy] = useState(false), [pending, setPending] = useState<{ request: ProposalRequest; nonce: string } | null>(null);
  const [selected, setSelected] = useState<string[]>([]), [displaced, setDisplaced] = useState<string[]>([]);
  const [relation, setRelation] = useState("UNRESOLVED"), [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState<ProposalRequest["evidence"]>([]);
  const [option, setOption] = useState(""), [quote, setQuote] = useState(""), [purpose, setPurpose] = useState("CONDITION"), [bound, setBound] = useState<string[]>([]);
  const v = result?.ok ? result.value : null;
  const rows = v?.review.snapshot.conditions ?? [], ids = rows.filter(r => selected.includes(r.condition.condition_id)).map(r => r.condition.condition_id);
  const chosen = rows.filter(r => ids.includes(r.condition.condition_id));
  const resolved = relation !== "UNRESOLVED";
  const valid = ids.length >= 2 && new Set(chosen.map(r => r.condition.scope)).size >= 2 && !!reason.trim()
    && (!resolved || chosen.every(r => r.disposition === "INHERITED" || (r.disposition === "LOCAL" && r.condition.state === "KNOWN")))
    && (relation !== "EXCEPTION" || (displaced.length > 0 && displaced.length < ids.length))
    && (!resolved || (ids.every(id => evidence.some(e => e.purpose === "CONDITION" && e.condition_ids.includes(id))) && evidence.some(e => e.purpose === "RELATION")))
    && evidence.length <= 200;
  const source = v?.evidence_options.find(e => `${e.block_id}:${e.member_id}` === option);
  const bindings = purpose === "RELATION" ? ids : ids.filter(id => bound.includes(id));
  const canAdd = !!source && !!quote.trim() && quote.length <= 20000 && source.text.includes(quote) && bindings.length > 0 && evidence.length < 200;
  function resetDraft() { setSelected([]); setDisplaced([]); setRelation("UNRESOLVED"); setReason(""); setEvidence([]); setOption(""); setQuote(""); setBound([]); }
  async function reload(after?: string) {
    if (active.current) return;
    active.current = true; setBusy(true); setResult(null);
    try {
      const next = await loadProposalContext(task, plan, after);
      if (after && next.ok && v) {
        if (next.value.review_hash !== v.review_hash) setResult({ ok: false, error: "来源已变化，请重新读取当前条件。" });
        else setResult({ ok: true, value: { ...next.value, evidence_options: [...v.evidence_options, ...next.value.evidence_options] } });
      } else { setResult(next); if (next.ok) { resetDraft(); setPending(null); } }
    } catch { setResult({ ok: false, error: "读取失败，请核对权限后重试。" }); }
    finally { active.current = false; setBusy(false); }
  }
  async function save(item: { request: ProposalRequest; nonce: string }) {
    if (active.current) return;
    active.current = true; setBusy(true); setPending(item); setResult(null);
    try {
      const receipt = await proposeRelation(task, plan, item.request, item.nonce);
      if (receipt.ok) { router.push(relationPath(task, plan, receipt.value.proposal_id)); return; }
      setResult(receipt);
    } catch { setResult({ ok: false, error: "保存回执未知，请重试原请求或查看已保存提案。" }); }
    active.current = false; setBusy(false);
  }
  return <main id="main-content" className="page-shell human-test-shell investigation-shell">
    <nav className="breadcrumbs"><Link href={crossLevelPath(task, plan)}>返回跨层级条件总览</Link><Link href={relationPath(task, plan)}>查看已保存提案</Link></nav>
    <h1>新建关系提案</h1>
    <aside className="fixture-notice">提案仅供独立审核，不执行资格裁决。整体资格仍为 UNCERTAIN（待确认），提案人不能审核自己的提案。</aside>
    <button className="button button-secondary" disabled={busy} onClick={() => void reload()}>重新读取当前条件</button>
    <p>重新读取成功后会清空草稿，请基于当前条件重新填写。</p>
    {busy ? <p role="status">正在核对与保存，请等待…</p> : null}
    {result && !result.ok ? <section role="alert" className="human-test-panel"><p>{result.error}</p>{pending ? <button disabled={busy} onClick={() => void save(pending)}>重试原请求</button> : null}</section> : null}
    {v ? <form className="review-form" onSubmit={e => { e.preventDefault(); if (valid) void save({ request: { target_plan_id: plan, expected_review_hash: v.review_hash, condition_ids: ids, relation, displaced_condition_ids: ids.filter(id => displaced.includes(id)), reason, evidence }, nonce: crypto.randomUUID() }); }}>
      <section className="human-test-panel"><h2>1. 选择完整条件范围中的关联条件</h2><p>至少选择两个条件，且来自不同层级。更改选择会清空已添加证据与替代对象。</p>
        {rows.map(({ condition: c, disposition }) => { const raw = originalCondition(v.review, c); return <div className="human-test-panel" key={c.condition_id}>
          <label className="investigation-check"><input type="checkbox" aria-label={`选择条件 ${c.condition_id}`} checked={ids.includes(c.condition_id)} onChange={e => { setSelected(e.target.checked ? [...ids, c.condition_id] : ids.filter(id => id !== c.condition_id)); setDisplaced([]); setEvidence([]); setBound([]); }} /> {scopes[c.scope]} · {raw?.field ?? c.field_name}</label>
          <p>原始条件：{raw?.value == null ? "未披露" : typeof raw.value === "object" ? JSON.stringify(raw.value) : String(raw.value)}</p>
          {raw?.note ? <p>原备注：{raw.note}</p> : null}<p>状态：{c.state} · 适用范围：{disposition}</p>
        </div>; })}
      </section>
      <section className="human-test-panel"><h2>2. 描述关系</h2>
        <label>关系类型<select value={relation} onChange={e => { setRelation(e.target.value); setDisplaced([]); }}>{Object.entries(relationKinds).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <p>累积、例外和冲突仅可使用已生效的继承条件或有依据的岗位条件。信息不足时保留“关系尚未确定”。</p>
        {relation === "EXCEPTION" ? <fieldset><legend>被例外替代的条件（至少一条，不能为全部）</legend>{chosen.map(r => <label className="investigation-check" key={r.condition.condition_id}><input type="checkbox" checked={displaced.includes(r.condition.condition_id)} onChange={e => setDisplaced(e.target.checked ? [...displaced, r.condition.condition_id] : displaced.filter(id => id !== r.condition.condition_id))} />{scopes[r.condition.scope]} · {r.condition.condition_id}</label>)}</fieldset> : null}
        <label>提案理由<textarea required maxLength={2000} value={reason} onChange={e => setReason(e.target.value)} /></label>
      </section>
      <section className="human-test-panel"><h2>3. 添加逐字官方证据</h2><p>已确定关系需要覆盖每条所选条件的条件证据，以及绑定全部所选条件的关系证据。引文必须逐字包含在所选原文块中。</p>
        <label>官方原文块<select value={option} onChange={e => { setOption(e.target.value); setQuote(""); }}><option value="">请选择原文块</option>{v.evidence_options.map(e => <option key={`${e.block_id}:${e.member_id}`} value={`${e.block_id}:${e.member_id}`}>{e.material_id} · {e.text.slice(0, 90)}</option>)}</select></label>
        {v.next_cursor ? <button className="button button-secondary" type="button" disabled={busy} onClick={() => void reload(v.next_cursor!)}>加载更多原文块</button> : null}
        {source ? <><blockquote style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{source.text}</blockquote><a href={source.source_url} target="_blank" rel="noreferrer">查看官方来源</a><details><summary>查看原文定位</summary><pre className="investigation-json">{JSON.stringify(source.locator, null, 2)}</pre></details></> : null}
        <label>证据用途<select value={purpose} onChange={e => setPurpose(e.target.value)}><option value="CONDITION">条件证据</option><option value="RELATION">关系证据（全部所选条件）</option></select></label>
        {purpose === "CONDITION" ? <fieldset><legend>此引文支持的条件</legend>{chosen.map(r => <label className="investigation-check" key={r.condition.condition_id}><input type="checkbox" checked={bound.includes(r.condition.condition_id)} onChange={e => setBound(e.target.checked ? [...bound, r.condition.condition_id] : bound.filter(id => id !== r.condition.condition_id))} />{scopes[r.condition.scope]} · {r.condition.condition_id}</label>)}</fieldset> : null}
        <label>逐字引文<textarea maxLength={20000} value={quote} onChange={e => setQuote(e.target.value)} /></label>
        <button className="button button-secondary" type="button" disabled={!canAdd} onClick={() => { const item = { member_id: source!.member_id, block_id: source!.block_id, quote, purpose, condition_ids: bindings }; if (!evidence.some(e => JSON.stringify(e) === JSON.stringify(item))) setEvidence([...evidence, item]); }}>添加证据</button>
        {quote && !canAdd ? <p>请选择原文块、绑定条件，并确保引文为原文的逐字片段。</p> : null}
        {evidence.map((e, i) => <article key={i}><p>{e.purpose === "RELATION" ? "关系证据" : "条件证据"} · {e.condition_ids.join("、")}</p><blockquote style={{ whiteSpace: "pre-wrap" }}>{e.quote}</blockquote><button className="button button-secondary" type="button" onClick={() => setEvidence(evidence.filter((_, n) => i !== n))}>移除证据 {i + 1}</button></article>)}
      </section>
      {!valid ? <p>请检查跨层级选择、理由、例外替代范围及证据覆盖。</p> : null}
      <button className="button button-primary" type="submit" disabled={!valid || busy}>保存关系提案</button>
    </form> : null}
  </main>;
}
