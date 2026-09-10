"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { loadGroupRulePreviewAction } from "../../app/review/investigations/group-rule-actions";
import { loadGroupRuleReviewAction, submitGroupRuleReviewAction } from "../../app/review/investigations/group-rule-review-actions";
import { groupRulePath, groupRuleReasons, type GroupRuleResult } from "../../lib/group-rules";
import { evidenceAuthorities, groupRuleReviewPath, type GroupRuleAssessment, type GroupRuleReviewCommand, type GroupRuleReviewResult } from "../../lib/group-rule-review";
import { EvidenceCheckDetail } from "./evidence-check";
type View = { kind: "preview"; result: GroupRuleResult } | { kind: "review"; result: GroupRuleReviewResult };
export default function GroupRuleReview({ taskId, factId, savedId, initial }: { taskId: string; factId: string; savedId?: string; initial: View }) {
  const router = useRouter(), active = useRef(false);
  const [view, setView] = useState<View | null>(initial), [busy, setBusy] = useState(false), [retry, setRetry] = useState<GroupRuleReviewCommand | null>(null);
  const record = view?.kind === "review" && view.result.ok ? view.result.value : null;
  const preview = record?.result.preview ?? (view?.kind === "preview" && view.result.ok ? view.result.value : null);
  const resolvedFactId = record?.fact_preparation_id || factId;
  async function reload() {
    if (active.current) return; active.current = true; setBusy(true); setView(null); setRetry(null);
    try { setView(savedId ? { kind: "review", result: await loadGroupRuleReviewAction(taskId, savedId) } : { kind: "preview", result: await loadGroupRulePreviewAction(taskId, factId) }); }
    catch { setView({ kind: "review", result: { ok: false, kind: "unavailable", error: "当前审核不可用，旧内容已隐藏。" } }); }
    finally { active.current = false; setBusy(false); }
  }
  async function submit(command: GroupRuleReviewCommand) {
    if (active.current) return; active.current = true; setBusy(true); setView(null); setRetry(null);
    let navigating = false;
    try {
      const result = await submitGroupRuleReviewAction(taskId, command);
      if (result.ok && !savedId) {
        // Do not expose forms on the start page while an older RSC response
        // is navigating to the saved address. The new page owns further edits.
        router.replace(groupRuleReviewPath(taskId, result.value.preparation_id));
        navigating = true; return;
      }
      setView({ kind: "review", result });
      if (!result.ok && result.kind === "unavailable") setRetry(command);
    } catch { setView({ kind: "review", result: { ok: false, kind: "unavailable", error: "未取得提交回执，可明确重试原请求。" } }); setRetry(command); }
    finally { if (!navigating) { active.current = false; setBusy(false); } }
  }
  return <main id="main-content" className="page-shell human-test-shell investigation-shell">
    <nav className="breadcrumbs" aria-label="面包屑">{resolvedFactId ? <Link href={groupRulePath(taskId, resolvedFactId)}>返回只读规则预览</Link> : <Link href={`/review/investigations/${encodeURIComponent(taskId)}`}>返回调查任务</Link>}</nav>
    <h1>单位组规则独立审核</h1>
    <aside className="fixture-notice">规则批准仅针对当前单位组。岗位适用与继承尚未裁决，整体资格仍为 UNCERTAIN。</aside>
    <button className="button button-secondary" disabled={busy} onClick={() => void reload()}>{busy ? "正在核对…" : "重新读取当前审核"}</button>
    {view && !view.result.ok ? <section role="alert" className="human-test-panel"><h2>当前审核不可用</h2><p>{view.result.error}</p></section> : null}
    {retry ? <button className="button" disabled={busy} onClick={() => void submit(retry)}>重试原提交（相同请求）</button> : null}
    {preview ? <>
      <section className="human-test-panel"><h2>{preview.result.target.label}</h2><p>组版本 {preview.result.target.version} · {preview.result.target.public_id}</p>
        <p>原组字段 {preview.result.rows.length} 项 · 可审核规则 {preview.result.rows.filter(r => r.proposed_rule_payload).length} 项 · 其他层级 {preview.result.fact_review.result.excluded_rows.length} 项保留排除记录。</p>
        {!record ? <><p>先保存当前规则候选，再逐条审核证据；保存不会批准规则。</p><button className="button" disabled={busy || !preview.result.fact_review.fact_set} onClick={() => void submit({ kind: "prepare", fact_preparation_id: factId, expected_preview_hash: preview.result_hash })}>保存候选并进入审核</button></> : <p role="status">候选已保存 · 审核记录 {record.preparation_id}</p>}
      </section>
      {preview.result.rows.map((row, i) => {
        const source = preview.result.fact_review.result.rows[i], candidate = record?.result.rows[i].rule_candidate_id, decision = candidate ? record?.decisions[candidate] : null;
        return <article className="human-test-panel group-fact-row" key={row.source_index} aria-label={`规则审核：${source.original_field}`}>
          <div><h2>{source.original_field}</h2><p>原始候选：{source.raw_value ?? "未披露"}</p><p>调查状态：{source.original_status}</p>{source.original.note ? <p>{source.original.note}</p> : null}
            {source.evidence.map((e, n) => <div key={n}><blockquote>{e.reference.quote}</blockquote><EvidenceCheckDetail evidence={e.reference} receipt={e.check_reference} />
              <a href={`/review/investigations/${encodeURIComponent(taskId)}/materials/${encodeURIComponent(e.reference.artifact_id)}`}>查看原件 · {e.reference.artifact_id}</a>
              <details><summary>查看原定位与证据块</summary><pre className="investigation-json">{JSON.stringify(e.reference.locator, null, 2)}</pre>{e.binding ? <blockquote>{e.binding.block_text}</blockquote> : <p>尚未机械核验，不计为 PASS。</p>}</details>
            </div>)}
          </div><div><h3>规则与证据评估</h3><p>{groupRuleReasons[row.reason_code]}</p>
            {row.proposed_rule_payload ? <><p>{row.proposed_rule_payload.reason_template}</p><p>规则值：{JSON.stringify(row.proposed_rule_payload.value)}</p></> : <p>没有可执行规则，该条件保留在完整分母中。</p>}
            {decision ? <section role="status"><h4>审核结果：{({ APPROVE: "已批准", REJECT: "已拒绝", NEEDS_ADJUDICATION: "待裁决" })[decision.decision]}</h4><p>{decision.reason}</p><p>审核时间 {decision.created_at}</p></section> : null}
            {record && candidate && (!decision || decision.decision === "NEEDS_ADJUDICATION") ? <RuleForm key={`${candidate}-${record.history.length}`} refs={row.evidence_ref_ids} busy={busy} onSubmit={(decision, reason, evidence) => submit({ kind: "decision", preparation_id: record.preparation_id, expected_preparation_hash: record.result_hash, rule_candidate_id: candidate, decision, reason, evidence })} /> : null}
          </div>
        </article>;
      })}
      {record ? <details className="human-test-panel"><summary>查看全部审核历史与证据评估</summary><pre className="investigation-json">{JSON.stringify(record.history, null, 2)}</pre></details> : null}
      <details className="human-test-panel"><summary>查看依据与完整分母</summary><pre className="investigation-json">{JSON.stringify({ source_row_count: preview.result.fact_review.result.source_row_count, excluded_rows: preview.result.fact_review.result.excluded_rows, result_hash: record?.result_hash ?? preview.result_hash }, null, 2)}</pre></details>
    </> : null}
  </main>;
}
function RuleForm({ refs, busy, onSubmit }: { refs: string[]; busy: boolean; onSubmit: (decision: "APPROVE" | "REJECT" | "NEEDS_ADJUDICATION", reason: string, evidence: GroupRuleAssessment[]) => Promise<void> }) {
  const [decision, setDecision] = useState<"" | "APPROVE" | "REJECT" | "NEEDS_ADJUDICATION">(""), [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState<GroupRuleAssessment[]>(refs.map(id => ({ evidence_ref_id: id, authority: null, relation: null, effective_at: null, applicability: "UNRESOLVED", reason: "" })));
  function update(index: number, value: Partial<GroupRuleAssessment>) { setEvidence(old => old.map((e, i) => i === index ? { ...e, ...value } : e)); }
  const complete = decision && reason.trim() && (decision !== "APPROVE" || evidence.every(e => e.authority && e.relation && e.effective_at && e.applicability === "APPLIES_TO_EXACT_TARGET" && e.reason.trim()));
  return <form className="human-test-form" onSubmit={event => { event.preventDefault(); if (complete) void onSubmit(decision as "APPROVE" | "REJECT" | "NEEDS_ADJUDICATION", reason.trim(), evidence.filter(e => decision === "APPROVE" || e.reason.trim()).map(e => ({ ...e, reason: e.reason.trim() }))); }}>
    {evidence.map((e, i) => <fieldset key={e.evidence_ref_id}><legend>证据 {i + 1} 独立评估</legend><small>引用 {e.evidence_ref_id}</small>
      <label>权威类别<select value={e.authority ?? ""} onChange={event => update(i, { authority: event.target.value as GroupRuleAssessment["authority"] || null })}><option value="">尚未评估</option>{Object.entries(evidenceAuthorities).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>与规则的关系<select value={e.relation ?? ""} onChange={event => update(i, { relation: event.target.value as GroupRuleAssessment["relation"] || null })}><option value="">尚未评估</option><option value="SUPPORTS">支持</option><option value="CONTRADICTS">冲突</option></select></label>
      <label>官方材料生效时间（本地时区）<input type="datetime-local" onChange={event => update(i, { effective_at: event.target.value ? new Date(event.target.value).toISOString() : null })} /></label>
      <label>适用范围<select value={e.applicability} onChange={event => update(i, { applicability: event.target.value as GroupRuleAssessment["applicability"] })}><option value="UNRESOLVED">尚未确定</option><option value="APPLIES_TO_EXACT_TARGET">适用于当前单位组及版本</option></select></label>
      <label>证据评估说明<textarea maxLength={2000} value={e.reason} onChange={event => update(i, { reason: event.target.value })} /></label>
    </fieldset>)}
    <label>审核决定<select value={decision} onChange={event => setDecision(event.target.value as typeof decision)}><option value="">请选择</option><option value="APPROVE">批准当前组规则</option><option value="REJECT">拒绝候选</option><option value="NEEDS_ADJUDICATION">提交待裁决</option></select></label>
    <label>审核说明<textarea maxLength={2000} value={reason} onChange={event => setReason(event.target.value)} /></label>
    <button className="button" disabled={busy || !complete} type="submit">提交独立审核</button>
  </form>;
}
