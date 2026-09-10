"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { loadGroupApplicabilityReview, saveGroupApplicabilityDecision } from "../../app/review/investigations/group-applicability-decision-actions";
import type { GroupApplicabilityIdentity, GroupApplicabilityResult } from "../../lib/group-applicability";
import type { GroupApplicabilityRequest, GroupApplicabilityReviewView } from "../../lib/group-applicability-decisions";
import { applicabilityOutcomes, type ApplicabilityOutcome, type ApplicabilitySelection } from "../../lib/rule-applicability";

export default function GroupApplicability({ identity, initial }: { identity: GroupApplicabilityIdentity; initial: GroupApplicabilityResult<GroupApplicabilityReviewView> }) {
  const [result, setResult] = useState<typeof initial | null>(initial), [busy, setBusy] = useState(false);
  const active = useRef(false);
  const [outcome, setOutcome] = useState<ApplicabilityOutcome | "">("");
  const [reason, setReason] = useState("");
  const [selections, setSelections] = useState<Record<string, ApplicabilitySelection>>({});
  const [pending, setPending] = useState<{ request: GroupApplicabilityRequest; nonce: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  function resetForm() { setOutcome(""); setReason(""); setSelections({}); setPending(null); }
  async function read(after: string | null = null) {
    if (active.current) return;
    active.current = true; setBusy(true);
    const old = result?.ok ? result.value : null;
    const expected = old?.context_hash;
    setResult(null);
    try {
      const next = await loadGroupApplicabilityReview(identity, after);
      if (after && next.ok && (next.value.context_hash !== expected || next.value.decisions.latest?.decision_id !== old?.decisions.latest?.decision_id)) {
        setResult({ ok: false, error: "上下文已变化，旧内容已隐藏，请重新读取首页。" }); return;
      }
      setResult(after && next.ok && old ? { ok: true, value: { ...next.value, evidence_options: [...new Map([...old.evidence_options, ...next.value.evidence_options].map(e => [`${e.member_id}:${e.block_id}`, e])).values()] } } : next);
      if (!after && next.ok) resetForm();
    } catch { setResult({ ok: false, error: "当前读取失败，旧内容已隐藏。" }); }
    finally { active.current = false; setBusy(false); }
  }
  const view = result?.ok ? result.value : null;
  const facts = view?.source_review.result.preview.result.fact_review.result;
  const source = facts?.group_source;
  const selectedField = facts?.rows.find(row => row.source_index === view?.candidate.source_index);
  const selectedRule = view?.candidate.proposed_rule_payload;
  async function save() {
    if (active.current) return;
    let submission = pending;
    if (!submission) {
      if (!view || !outcome || !reason.trim()) { setNotice("请选择决定并填写理由。"); return; }
      const evidence = Object.values(selections);
      if ((outcome !== "NEEDS_ADJUDICATION" && !evidence.length) || evidence.some(e => !e.quote.trim() || !view.evidence_options.find(o => o.member_id === e.member_id && o.block_id === e.block_id)?.text.includes(e.quote))) {
        setNotice("适用或不适用必须引用当前原文中的连续文字，不能改写。"); return;
      }
      submission = { nonce: crypto.randomUUID(), request: { contract_version: "group-applicability-decision/1.0.0", target_plan_id: identity.target_plan_id, source_rule_preparation_id: identity.source_rule_preparation_id, source_rule_candidate_id: identity.source_rule_candidate_id, context_hash: view.context_hash, previous_decision_id: view.decisions.latest?.decision_id ?? null, outcome, reason, evidence } };
    }
    active.current = true; setBusy(true); setPending(submission); setResult(null); setNotice(null);
    try {
      const saved = await saveGroupApplicabilityDecision(identity, submission.request, submission.nonce);
      if (!saved.ok) { setResult(saved); if (saved.kind !== "unavailable") setPending(null); return; }
      setPending(null);
      const next = await loadGroupApplicabilityReview(identity);
      if (next.ok && !next.value.decisions.history.some(d => d.decision_id === saved.value.decision_id && d.request_hash === saved.value.request_hash)) {
        setResult({ ok: false, error: "保存回执尚未出现在当前历史中，请重新读取。" }); return;
      }
      setResult(next);
      if (next.ok) { resetForm(); setNotice("决定已保存并核对，后续更正将追加记录。"); }
    } catch { setResult({ ok: false, error: "回执未确认，请重试原请求或重新读取。" }); }
    finally { active.current = false; setBusy(false); }
  }
  return <main id="main-content" className="page-shell human-test-shell investigation-shell">
    <nav className="breadcrumbs"><Link href={`/review/investigations/${identity.task_id}/unit-plans/${identity.target_plan_id}`}>返回岗位条件快照</Link></nav>
    <h1>组规则与岗位依据核对</h1>
    <aside className="fixture-notice">独立核对组规则是否适用于此岗位。适用决定不自动继承规则，整体资格仍不确定。</aside>
    <button className="button button-secondary" disabled={busy} onClick={() => void read()}>{busy ? "正在核对…" : "重新读取当前上下文"}</button>
    {result && !result.ok ? <section role="alert" className="human-test-panel"><h2>当前上下文不可用</h2><p>{result.error}</p></section> : null}
    {notice ? <p role="status">{notice}</p> : null}
    {pending ? <button className="button button-secondary" disabled={busy} onClick={() => void save()}>重试原请求</button> : null}
    {view && facts && source ? <>
      <section className="human-test-panel"><h2>{source.group_identity.label} → {view.context.target_entity_id}</h2>
        <p>组版本 {source.group_identity.version} · 岗位版本 {view.context.target.unit_version} · {view.decisions.latest ? applicabilityOutcomes[view.decisions.latest.request.outcome] : "尚未裁决"}</p>
        <p>原组字段 {facts.rows.length} 项 · 原组成员 {source.source.members.length} 项；未处理项仍完整保留。</p>
        <Link href={`/review/investigations/${identity.task_id}/group-rules/${identity.source_rule_preparation_id}`}>查看组规则独立审核</Link>
      </section>
      <div className="group-fact-row">
        <section className="human-test-panel review-form" style={{ alignContent: "start" }}><h2>当前官方原文</h2><p>已加载 {view.evidence_options.length} 段；分页只改变阅读位置，不表示证据已全部核验。</p>
          {view.evidence_options.map((e, index) => { const key = `${e.member_id}:${e.block_id}`, selected = selections[key]; return <article key={key}><blockquote>{e.text}</blockquote><p><Link href={`/review/investigations/${identity.task_id}/materials/${encodeURIComponent(e.material_id)}`}>下载原件 · {e.material_id}</Link></p><details><summary>证据定位</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(e.locator, null, 2)}</pre></details>
            <label className="investigation-check"><input type="checkbox" checked={!!selected} disabled={busy || (!selected && Object.keys(selections).length >= 20)} onChange={event => { const checked = event.target.checked; setSelections(old => { const next = { ...old }; if (checked) next[key] = { member_id: e.member_id, block_id: e.block_id, quote: e.text.length <= 20000 ? e.text : "" }; else delete next[key]; return next; }); }} />引用原文 {index + 1}</label>
            {selected ? <label>引用文字 {index + 1}<textarea rows={4} maxLength={20000} value={selected.quote} onChange={event => setSelections(old => ({ ...old, [key]: { ...selected, quote: event.target.value } }))} /></label> : null}
          </article>; })}
          {!view.evidence_options.length ? <p>当前页没有可读取段落，不能据此判定没有限制。</p> : null}
          {view.next_cursor ? <button className="button button-secondary" disabled={busy} onClick={() => void read(view.next_cursor)}>读取下一页原文</button> : null}
        </section>
        <section className="human-test-panel"><h2>组条件与成员</h2>
          {facts.rows.map(row => <article key={row.source_index}><h3>{row.original_field}</h3><p>{row.original.value ?? "信息不足"} · {row.original_status}</p></article>)}
          <h3>完整成员清单</h3><ul>{source.source.members.map(m => <li key={m.entity_id}>{m.entity_id} · {m.state === "BOUND" ? "已有岗位绑定" : "尚未处理"}</li>)}</ul>
          <h3>本条组规则批准</h3><p>{view.approval.reason}</p><p>该批准针对单位组，尚不是岗位适用决定。</p>
          <h3>岗位未完成项</h3><p>{view.target_plan.plan.manifest.upstream_blockers.join("、") || "仍需独立核对完整适用范围"}</p>
          <form className="review-form" onSubmit={event => { event.preventDefault(); void save(); }}>
            <h3>本次审核的组规则：{selectedField?.original_field ?? "字段未能确认"}</h3>
            <p>{selectedField?.original.value ?? "信息不足"}</p>
            <p>本次决定仅针对这一条组规则，不代表整组条件已适用于岗位。</p>
            {selectedRule ? <details><summary>核对规则字段、运算符与值</summary><pre className="investigation-json">{JSON.stringify({ field: selectedRule.field, operator: selectedRule.operator, value: selectedRule.value }, null, 2)}</pre></details> : null}
            <h3>追加适用决定</h3><p>适用或不适用需引用左侧原文；待裁决可以只填理由。</p>
            <label>适用性决定<select value={outcome} disabled={busy} onChange={event => setOutcome(event.target.value as ApplicabilityOutcome | "")}><option value="">请选择</option>{Object.entries(applicabilityOutcomes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
            <label>决定理由<textarea rows={4} maxLength={2000} value={reason} disabled={busy} onChange={event => setReason(event.target.value)} /></label>
            <button className="button button-primary" disabled={busy} type="submit">保存适用性决定</button>
          </form>
          <h3>适用决定历史</h3>
          {!view.decisions.history.length ? <p>尚无适用决定。</p> : null}
          {view.decisions.history.map(d => <details key={d.decision_id}><summary>第 {d.sequence} 次 · {applicabilityOutcomes[d.request.outcome]}</summary><p>{d.request.reason}</p><p>审核人 {d.reviewer_id} · {d.created_at}</p>{d.evidence_snapshot.map((e, index) => <blockquote key={index}>{e.quote}</blockquote>)}<pre className="investigation-json">{JSON.stringify(d, null, 2)}</pre></details>)}
        </section>
      </div>
    </> : null}
  </main>;
}
