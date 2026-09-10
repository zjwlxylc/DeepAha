"use client";

import Link from "next/link";
import { useRef, useState, type FormEvent } from "react";
import { loadGroupFactStartAction, loadGroupFactRecordAction, submitGroupFactAction } from "../../app/review/investigations/group-fact-actions";
import { groupFactRecordPath, type GroupFactResult, type GroupFactCommand, type GroupFactData } from "../../lib/group-facts";
import { groupRecordPath } from "../../lib/group-sources";
import { EvidenceCheckDetail } from "./evidence-check";

const labels = { APPROVE: "批准字段", REJECT: "拒绝候选", UNKNOWN: "保留未知", NEEDS_ADJUDICATION: "需要进一步裁决" };
export default function GroupFactReview({ taskId, groupId, prepId: initialPrepId, initialResult }: { taskId: string; groupId?: string; prepId?: string; initialResult: GroupFactResult }) {
  const [data, setData] = useState<GroupFactData | null>(initialResult.ok ? initialResult.value : null);
  const [prepId, setPrepId] = useState(initialPrepId ?? (initialResult.ok ? initialResult.value.record?.preparation_id : null));
  const [error, setError] = useState(initialResult.ok ? null : initialResult.error);
  const [retry, setRetry] = useState<GroupFactCommand | null>(null);
  const [busy, setBusy] = useState(false), inFlight = useRef(false);
  async function perform(command?: GroupFactCommand) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(null);
    try {
      const result = command ? await submitGroupFactAction(taskId, command) : prepId ? await loadGroupFactRecordAction(taskId, prepId) : await loadGroupFactStartAction(taskId, groupId ?? "");
      if (result.ok) { setData(result.value); setPrepId(result.value.record?.preparation_id ?? null); setRetry(null); }
      else { setData(null); setError(result.error); setRetry(command && result.kind === "unavailable" ? command : null); }
    } catch { setData(null); setError("暂未取得当前审核记录，旧内容已隐藏。请明确重试或重新读取。"); setRetry(command ?? null); }
    finally { inFlight.current = false; setBusy(false); }
  }
  const record = data?.record, source = data?.source.preview.registration;
  const candidates = record?.result.rows.filter(row => row.candidate_id) ?? [];
  const final = candidates.length > 0 && candidates.every(row => record!.decisions[row.candidate_id!] && record!.decisions[row.candidate_id!].decision !== "NEEDS_ADJUDICATION");
  const canPromote = final && candidates.some(row => ["APPROVE", "UNKNOWN"].includes(record!.decisions[row.candidate_id!].decision));
  function decide(event: FormEvent<HTMLFormElement>, candidateId: string) {
    event.preventDefault(); if (!record) return;
    const form = new FormData(event.currentTarget);
    void perform({ kind: "decision", preparation_id: record.preparation_id, expected_preparation_hash: record.result_hash, candidate_id: candidateId,
      decision: String(form.get("decision")) as "APPROVE", evidence_support: String(form.get("evidence_support")) as "SUPPORTED",
      precedence_check: String(form.get("precedence_check")) as "PASSED", reason: String(form.get("reason")) });
  }
  return <main id="main-content" className="page-shell human-test-shell investigation-shell">
    <nav className="breadcrumbs" aria-label="面包屑"><Link href={`/review/investigations/${encodeURIComponent(taskId)}`}>返回调查任务</Link>{source ? <Link href={groupRecordPath(taskId, source.group_binding_id)}>查看已登记组来源</Link> : null}</nav>
    <h1>单位组字段审核</h1>
    <aside className="fixture-notice">候选与精确引用不等于已批准事实。组事实保存不批准岗位继承、规则或完整资格，整体资格仍为 UNCERTAIN。</aside>
    {error ? <section role="alert" className="human-test-panel"><h2>组事实记录暂不可用</h2><p>{error}</p></section> : null}
    <div className="announcement-snapshot-actions"><button className="button button-secondary" disabled={busy} onClick={() => void perform()}>{busy ? "正在核对…" : "重新读取当前审核记录"}</button>
      {retry ? <button className="button button-primary" disabled={busy} onClick={() => void perform(retry)}>重试原审核请求</button> : null}</div>
    {data && source ? <section className="human-test-panel"><h2>{source.group_identity.label}</h2><p>组版本 {source.group_identity.version} · 所属机会版本 {source.source.opportunity_version}</p>
      <p className="investigation-hash">稳定组标识：{source.group_identity.public_id}</p>
      {!record ? <><p>准备会保留全部组字段和未处理项，不会自动批准。</p><button className="button button-primary" disabled={busy} onClick={() => void perform({ kind: "prepare", group_binding_id: source.group_binding_id, check_id: data.source.task.evidence_check!.check_id, expected_source_hash: source.source_hash })}>准备组字段候选</button></> : <>
        <Link prefetch={false} href={groupFactRecordPath(taskId, record.preparation_id)}>打开已保存审核记录</Link>
        <p>组字段 {record.result.rows.length} 项；可审核 {candidates.length} 项；待处理 {record.result.rows.length - candidates.length} 项。其他层级 {record.result.excluded_rows.length} 项保留排除记录。</p>
      </>}
    </section> : null}
    {record ? <>
      {!record.result.rows.length ? <p className="human-test-panel">原组没有字段，不会创建空事实集。</p> : null}
      {record.result.rows.map(row => {
        const decision = row.candidate_id ? record.decisions[row.candidate_id] : null;
        return <article key={row.source_index} className="human-test-panel group-fact-row" aria-label={`组字段：${row.original_field}`}>
          <div><h2>{row.original_field}</h2><p>原始候选：{row.raw_value ?? "未披露"}</p><p>调查状态：{row.original_status}</p>
            <p>{!row.candidate_id ? "待处理：尚无可审核候选" : row.abstained ? "规范候选：未知，不能批准为已知事实" : `规范候选：${JSON.stringify(row.normalized_value_candidate)}`}</p>
            {row.original.note ? <p>原备注：{row.original.note}</p> : null}
            {row.issue_codes.length ? <details><summary>查看待处理原因</summary><ul>{row.issue_codes.map((code, i) => <li key={i}>{code}</li>)}</ul></details> : null}
            {row.evidence.map((e, index) => <div key={index}><blockquote>{e.reference.quote}</blockquote><EvidenceCheckDetail evidence={e.reference} receipt={e.check_reference} />
              <a href={`/review/investigations/${encodeURIComponent(taskId)}/materials/${encodeURIComponent(e.reference.artifact_id)}`}>下载原件 · {e.reference.artifact_id}</a>
              <details><summary>查看原定位与证据块</summary><pre className="investigation-json">{JSON.stringify(e.reference.locator, null, 2)}</pre>{e.binding ? <><pre className="investigation-json">{JSON.stringify(e.binding.structural_locator, null, 2)}</pre><blockquote>{e.binding.block_text}</blockquote></> : <p>原件或定位尚未完成机械核验，不计为 PASS。</p>}</details>
            </div>)}
          </div><div>
            {decision ? <p role="status">审核：{labels[decision.decision]}。依据：{decision.reason}</p> : null}
            {row.candidate_id && !record.fact_set && (!decision || decision.decision === "NEEDS_ADJUDICATION") ? <form className="review-form" onSubmit={event => decide(event, row.candidate_id!)}>
              <fieldset disabled={busy}><legend>独立字段裁决</legend>
                <label>字段决定<select name="decision" required defaultValue=""><option value="">请选择</option>{Object.entries(labels).filter(([value]) => row.abstained ? value !== "APPROVE" : value !== "UNKNOWN").map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label>原文是否支持候选<select name="evidence_support" required defaultValue=""><option value="">请核对原文</option><option value="SUPPORTED">明确支持</option><option value="UNSUPPORTED">不支持</option><option value="UNKNOWN">尚不能确认</option></select></label>
                <label>更正与条件优先级<select name="precedence_check" required defaultValue=""><option value="">请核对优先级</option><option value="PASSED">已核对，无未解决冲突</option><option value="FAILED">存在冲突</option><option value="UNKNOWN">尚不能确认</option></select></label>
                <label>审核依据<textarea name="reason" required maxLength={2000} /></label><button className="button button-primary" type="submit">记录字段审核</button>
              </fieldset></form> : null}
          </div>
        </article>;
      })}
      <section className="human-test-panel"><h2>组事实集</h2>{record.fact_set ? <><p role="status">已保存组事实集 · {record.fact_set.status} · 版本 {record.fact_set.version}</p><p>{record.fact_set.reason}</p></> : canPromote ? <form className="review-form" onSubmit={event => { event.preventDefault(); void perform({ kind: "promote", preparation_id: record.preparation_id, expected_preparation_hash: record.result_hash, reason: String(new FormData(event.currentTarget).get("reason")) }); }}><fieldset disabled={busy}><legend>保存组事实集</legend><label>保存依据<textarea name="reason" required maxLength={2000} /></label><button className="button button-primary" type="submit">保存组事实集</button></fieldset></form> : <p>全部可审核候选完成终局裁决，且至少一项获批或明确保留未知后，才能保存。待处理原字段始终保留。</p>}</section>
      <details className="human-test-panel"><summary>查看来源分母与审核历史</summary><pre className="investigation-json">{JSON.stringify({ excluded_rows: record.result.excluded_rows, history: record.history, result_hash: record.result_hash }, null, 2)}</pre></details>
    </> : null}
  </main>;
}
