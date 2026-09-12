"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { loadRuleApplicabilityAction, saveRuleApplicabilityAction } from "../../app/review/investigations/rule-applicability-actions";
import { applicabilityOutcomes, type ApplicabilityEvidence, type ApplicabilityIdentity, type ApplicabilityOutcome, type ApplicabilityRequest, type ApplicabilitySelection, type ApplicabilityView } from "../../lib/rule-applicability";
import { materialPath, safeOfficialUrl } from "../../lib/investigation-evidence-links";

const evidenceKey = (item: Pick<ApplicabilityEvidence, "member_id" | "block_id">) => `${item.member_id}:${item.block_id}`;
const unavailable = "暂未取得最新回执。请重试原请求，或重新读取最新状态后再修改。";
const changed = "来源、岗位或上一决定已变化。请重新读取最新状态后核对。";
function ruleText(rule: ApplicabilityView["source_rule"]) {
  const fields: Record<string, string> = { education_level: "学历", major_code: "专业代码", hukou_region: "户籍", student_status: "在读／毕业状态", certificates: "证书", birth_date: "出生日期" };
  const operators: Record<string, string> = { GTE: "不低于", IN: "属于以下允许范围", CONTAINS_ALL: "需包含全部项目", BETWEEN: "位于以下区间" };
  const levels: Record<string, string> = { SECONDARY: "中等教育", ASSOCIATE: "专科", BACHELOR: "本科", MASTER: "硕士", DOCTORATE: "博士" };
  const value = rule.field === "education_level" && typeof rule.value === "string" ? levels[rule.value] ?? rule.value : JSON.stringify(rule.value);
  return `${fields[rule.field ?? ""] ?? rule.field ?? "组合条件"} ${operators[rule.operator] ?? rule.operator} ${value}`;
}
function EvidenceLinks({ taskId, evidence }: { taskId: string; evidence: Pick<ApplicabilityEvidence, "material_id" | "source_url"> }) {
  const official = safeOfficialUrl(evidence.source_url);
  return <p><a href={materialPath(taskId, evidence.material_id)} target="_blank" rel="noopener noreferrer">打开对应原件</a>{" · "}
    {official ? <a href={official} target="_blank" rel="noopener noreferrer">查看官方原文</a> : <span>官方地址不可用</span>}</p>;
}

export default function RuleApplicabilityReview({ identity, initialView, requestKey }: { identity: ApplicabilityIdentity; initialView: ApplicabilityView; requestKey: string }) {
  const [view, setView] = useState<ApplicabilityView | null>(initialView);
  const [nonce, setNonce] = useState(requestKey);
  const [outcome, setOutcome] = useState<ApplicabilityOutcome | "">("");
  const [reason, setReason] = useState("");
  const [selections, setSelections] = useState<Record<string, ApplicabilitySelection>>({});
  const [pendingRequest, setPendingRequest] = useState<{ request: ApplicabilityRequest; nonce: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const back = `/review/investigations/${encodeURIComponent(identity.task_id)}/unit-plans/${encodeURIComponent(identity.target_plan_id)}`;
  const locked = busy || pendingRequest !== null;

  function block(message: string) { setView(null); setError(message); setNotice(null); }
  async function readLatest(saved = false) {
    try {
      const result = await loadRuleApplicabilityAction(identity);
      if (!result.ok) { block(result.error); return; }
      setView(result.value); setOutcome(""); setReason(""); setSelections({});
      setPendingRequest(null); setNonce(crypto.randomUUID()); setError(null);
      setNotice(saved ? "决定已保存，并已读取最新状态。再次修改会追加新的决定。" : "已读取最新状态；请重新核对后填写决定。");
    } catch { block(saved ? "决定已保存，但暂未读到最新状态。请重新读取后再修改。" : "暂时无法读取最新状态，请稍后重试。"); }
  }
  async function refresh() {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true);
    try { await readLatest(); } finally { inFlight.current = false; setBusy(false); }
  }
  async function loadMore() {
    if (!view?.next_cursor || locked || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(null); setNotice(null);
    try {
      const result = await loadRuleApplicabilityAction(identity, view.next_cursor);
      if (!result.ok) { block(result.error); return; }
      const next = result.value;
      if (next.context_hash !== view.context_hash || next.latest?.decision_id !== view.latest?.decision_id) { block(changed); return; }
      const all = new Map(view.evidence_options.map(item => [evidenceKey(item), item]));
      for (const item of next.evidence_options) all.set(evidenceKey(item), item);
      setView({ ...next, evidence_options: [...all.values()] });
    } catch { block("暂时无法读取后续原文，请重新读取最新状态。"); }
    finally { inFlight.current = false; setBusy(false); }
  }
  async function save() {
    if (!view || inFlight.current) return;
    let submission = pendingRequest;
    if (!submission) {
      const evidence = Object.values(selections);
      if (!outcome || !reason.trim() || reason.length > 2000 || evidence.length > 20 || (outcome !== "NEEDS_ADJUDICATION" && !evidence.length)) {
        setError("请明确选择决定并填写理由；适用或不适用至少引用一块原文，最多 20 块。"); return;
      }
      if (evidence.some(item => !item.quote.trim() || item.quote.length > 20000 || !view.evidence_options.find(option => evidenceKey(option) === evidenceKey(item))?.text.includes(item.quote))) {
        setError("引文须为对应原文中连续的字面片段，保留原始文字，且不超过 20000 字符。"); return;
      }
      submission = { nonce, request: {
        target_plan_id: identity.target_plan_id, source_rule_preparation_id: identity.source_rule_preparation_id,
        source_rule_candidate_id: identity.source_rule_candidate_id, context_hash: view.context_hash,
        previous_decision_id: view.latest?.decision_id ?? null, outcome, evidence, reason,
      } };
    }
    inFlight.current = true; setBusy(true); setError(null); setNotice(null);
    try {
      const result = await saveRuleApplicabilityAction(identity, submission.request, submission.nonce);
      if (result.ok) { await readLatest(true); }
      else if (result.kind === "stale" || result.kind === "forbidden") { block(result.error); }
      else { setError(result.error); setPendingRequest(result.kind === "unavailable" ? submission : null); }
    } catch { setPendingRequest(submission); setError(unavailable); }
    finally { inFlight.current = false; setBusy(false); }
  }

  return <main id="main-content" className="investigation-shell human-test-shell page-shell">
    <Link href={back} prefetch={false}>返回条件快照</Link>
    <h1>公告规则适用性审阅</h1>
    <p>此记录只判断一条公告规则是否适用于一个明确岗位，不解除整体 UNCERTAIN，也不改写已有条件快照。</p>
    {error ? <p role="alert" className="form-error">{error}</p> : null}
    {notice ? <p role="status">{notice}</p> : null}
    <button className="button button-secondary" type="button" disabled={busy} onClick={refresh}>{busy ? "正在核对最新状态…" : "重新读取最新状态"}</button>
    {!view ? null : <>
      <section className="human-test-panel" aria-labelledby="applicability-source">
        <h2 id="applicability-source">来源公告</h2><p>{view.source_label}</p><p>规则：{ruleText(view.source_rule)}</p>
        <p>已独立批准的公告规则，其对本岗位的适用性仍需以下单独决定。</p>
        <details><summary>查看完整规则及来源绑定</summary><pre className="investigation-json">{JSON.stringify(view.source_rule, null, 2)}</pre>
          <p className="investigation-hash">来源准备：{identity.source_rule_preparation_id}；规则：{identity.source_rule_candidate_id}</p>
        </details>
      </section>
      <section className="human-test-panel" aria-labelledby="applicability-target">
        <h2 id="applicability-target">目标岗位</h2><p>{view.target_label}</p>
        <details><summary>查看岗位版本及本次绑定</summary><pre className="investigation-json">{JSON.stringify(view.context, null, 2)}</pre><p className="investigation-hash">本次绑定摘要：{view.context_hash}</p></details>
      </section>
      <section className="human-test-panel" aria-labelledby="applicability-history">
        <h2 id="applicability-history">适用性决定记录</h2>
        <p>{view.latest ? `当前决定：${applicabilityOutcomes[view.latest.request.outcome]}（第 ${view.latest.sequence} 次）` : "尚无适用性决定。"}</p>
        {view.history.map(item => <details key={item.decision_id}>
          <summary>第 {item.sequence} 次：{applicabilityOutcomes[item.request.outcome]}</summary>
          <p style={{ whiteSpace: "pre-wrap" }}>{item.request.reason}</p>
          <p>审核人：{item.reviewer_id}；记录时间：{item.created_at}</p>
          {item.request.evidence.map((evidence, index) => {
            const snapshot = item.evidence_snapshot.find(bound => evidenceKey(bound) === evidenceKey(evidence) && bound.quote === evidence.quote);
            return <div key={`${evidenceKey(evidence)}:${index}`}><blockquote style={{ whiteSpace: "pre-wrap" }}>{evidence.quote}</blockquote>{snapshot ? <EvidenceLinks taskId={identity.task_id} evidence={snapshot} /> : null}</div>;
          })}
          <details><summary>查看不可变回执与证据绑定</summary><pre className="investigation-json">{JSON.stringify(item, null, 2)}</pre></details>
        </details>)}
      </section>
      <form className="review-form human-test-panel" onSubmit={event => { event.preventDefault(); void save(); }}>
        <h2>追加适用性决定</h2>
        {pendingRequest ? <p>上次请求的回执尚未确认，已保留并锁定原始内容。重试会使用同一个请求；重新读取最新状态后可重新填写。</p> : <p>每次保存均引用当前最新决定，保留完整历史。请独立核对公告、目标岗位与引文。</p>}
        <label>适用性决定<select value={outcome} disabled={locked} onChange={event => setOutcome(event.target.value as ApplicabilityOutcome | "")}>
          <option value="">请选择</option>{Object.entries(applicabilityOutcomes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label>决定理由<textarea rows={4} maxLength={2000} value={reason} disabled={locked} onChange={event => setReason(event.target.value)} /></label>
        <section aria-labelledby="applicability-evidence">
          <h3 id="applicability-evidence">适用性原文依据</h3>
          <p>适用或不适用至少引用一块原文，最多 20 块；待裁决可仅填写理由。选中后可保留整块原文，或引用其中连续的字面片段。</p>
          {!view.evidence_options.length ? <p>当前没有可引用的原文块。可记录待裁决及理由。</p> : null}
          {view.evidence_options.map((item, index) => {
            const key = evidenceKey(item), selected = selections[key], number = index + 1;
            return <article className="human-test-panel" key={key} aria-label={`原文块 ${number}`}>
              <h4>原文 {number}</h4>
              <pre className="investigation-json">{item.text}</pre>
              <p className="investigation-hash">材料：{item.material_id}；来源成员：{item.member_id}</p>
              <EvidenceLinks taskId={identity.task_id} evidence={item} />
              <details><summary>查看原文位置</summary><pre className="investigation-json">{JSON.stringify({ document_id: item.document_id, evidence_ref_id: item.evidence_ref_id, block_id: item.block_id, locator: item.locator }, null, 2)}</pre></details>
              <label className="investigation-check"><input type="checkbox" checked={!!selected} disabled={locked || (!selected && Object.keys(selections).length >= 20)} onChange={event => {
                const checked = event.target.checked;
                setSelections(previous => { const next = { ...previous }; if (checked) next[key] = { member_id: item.member_id, block_id: item.block_id, quote: item.text.length <= 20000 ? item.text : "" }; else delete next[key]; return next; });
              }} />引用原文 {number}</label>
              {selected ? <>
                {item.text.length > 20000 ? <p>此原文超过单条引文上限，请从完整显示的原文中复制不超过 20000 字符的连续片段。</p> : null}
                <label>引用文字 {number}<textarea rows={4} maxLength={20000} value={selected.quote} disabled={locked} onChange={event => {
                  const quote = event.target.value; setSelections(previous => ({ ...previous, [key]: { ...previous[key], quote } }));
                }} /></label>
              </> : null}
            </article>;
          })}
          <p>{view.next_cursor ? `已加载 ${view.evidence_options.length} 块原文，仍有后续原文可读取。` : `已加载当前可引用的全部原文块，共 ${view.evidence_options.length} 块。`}</p>
          {view.next_cursor ? <button className="button button-secondary" type="button" disabled={locked} onClick={loadMore}>加载更多原文</button> : null}
        </section>
        <button className="button button-primary" type="submit" disabled={busy}>{busy ? "正在保存并核对…" : pendingRequest ? "重试原请求" : "保存适用性决定"}</button>
      </form>
    </>}
  </main>;
}
