"use client";

import { useActionState, useState } from "react";
import Link from "next/link";
import type { InvestigationTask } from "../../lib/investigations";
import { investigationRuleAction } from "../../app/review/investigations/actions";
import { readableLocator, readableValue } from "../../lib/guided-review";
import { Hidden, Question, useGuidedAnswers } from "./guided-controls";
import { ruleAuthorities, ruleRelations, ruleApplicability } from "../../lib/investigation-rule-options";

export default function GuidedRule({ task, requestKey, next }: { task: InvestigationTask; requestKey: string; next: string }) {
  const facts = task.fact_review!.current!, prep = task.rule_review!.current[0], row = prep.rows[0];
  const saved = row?.rule_candidate_id ? prep.decisions[row.rule_candidate_id] : null;
  const [reconsider, setReconsider] = useState(false);
  const [state, action, pending] = useActionState(investigationRuleAction, { error: null, message: null, taskId: null });
  const { answers: a, change, reset, requestKey: key } = useGuidedAnswers(task.draft_scope ? JSON.stringify(["guided-rule", task.draft_scope, task.task_id, task.delivery_hash, prep.binding_id, prep.rule_preparation_id, row?.rule_candidate_id, saved?.decision_id]) : null, requestKey, !!state.message);
  if (!row) return <p>这一页没有条件，请返回上一条。</p>;
  const questions = row.evidence.flatMap((e, i) => [
    { key: `authority:${e.evidence_ref_id}`, title: `证据 ${i + 1} 来自哪类原件？`, choices: Object.entries(ruleAuthorities) },
    { key: `relation:${e.evidence_ref_id}`, title: `证据 ${i + 1} 支持下面这条判断条件吗？`, choices: Object.entries(ruleRelations) },
    { key: `applicability:${e.evidence_ref_id}`, title: `证据 ${i + 1} 确实适用于当前岗位吗？`, choices: Object.entries(ruleApplicability) },
    { key: `time:${e.evidence_ref_id}`, title: `证据 ${i + 1} 的要求从什么时候生效？`, choices: [] },
  ]);
  const question = questions.find(q => !a[q.key]);
  const deferred = a.defer === "yes";
  const reason = deferred ? `本人暂不能确认规则，原因：${a.problem ?? ""}。${a.note ?? ""}` : `本人已逐条核对所列原件的来源、支持关系、岗位适用性和生效时间。${a.note ?? ""}`;
  const fields: Record<string, string | null> = { task_id: task.task_id, delivery_hash: task.delivery_hash, binding_id: prep.binding_id, check_id: prep.check_id,
    fact_preparation_id: facts.preparation_id, fact_set_id: prep.fact_set_id, entity_id: prep.entity_id, kind: "decision", workbench: "1", request_key: key,
    rule_preparation_id: prep.rule_preparation_id, rule_candidate_id: row.rule_candidate_id, decision: deferred ? "NEEDS_ADJUDICATION" : a.decision ?? "", reason };
  for (const e of row.evidence) {
    const id = e.evidence_ref_id;
    fields[`authority:${id}`] = deferred ? "" : a[`authority:${id}`] ?? "";
    fields[`relation:${id}`] = deferred ? "" : a[`relation:${id}`] ?? "";
    fields[`applicability:${id}`] = deferred ? "UNRESOLVED" : a[`applicability:${id}`] ?? "UNRESOLVED";
    fields[`effective_at:${id}`] = !deferred && a[`time:${id}`] ? `${a[`date:${id}`]}T${a[`clock:${id}`]}:00+08:00` : "";
    fields[`evidence_reason:${id}`] = reason;
  }
  const canApprove = row.evidence.length > 0 && row.evidence.every(e => a[`relation:${e.evidence_ref_id}`] === "SUPPORTS" && a[`applicability:${e.evidence_ref_id}`] === "APPLIES_TO_EXACT_TARGET");
  const source = prep.source_rows.find(s => s.candidate_id === row.candidate_id);
  const operators: Record<string, string> = { GTE: "不低于", IN: "必须属于", CONTAINS_ALL: "必须包含", BETWEEN: "必须位于区间" };
  return <div className="guided-question-layout">
    <div className="guided-comparison"><section className="guided-source"><h2>原件怎么写</h2>{row.evidence.map((e, i) => <div key={e.evidence_ref_id}><h3>证据 {i + 1}</h3><p>{readableLocator(e.structural_locator)}</p><blockquote>{e.text}</blockquote>
      {source?.evidence.filter(v => v.binding?.evidence_ref_id === e.evidence_ref_id).map((v, n) => <a key={n} href={`/review/investigations/${task.task_id}/materials/${encodeURIComponent(v.reference.artifact_id)}`}>打开对应原件</a>)}
    </div>)}</section><section className="guided-proposal"><p className="eyebrow">再核对一次 · 用于后续判断的条件</p><h2>{source?.original_field ?? row.field_name}</h2><p className="guided-value">{row.payload ? `${operators[row.payload.operator] ?? row.payload.operator} ${readableValue(row.payload.value)}` : "还不能形成明确判断条件"}</p><p>这一步单独核对判断逻辑，不会沿用上一轮的批准。</p></section></div>
    {!row.rule_candidate_id ? <section className="guided-card"><h2>这条内容仍需处理</h2><p>{row.fact_state === "UNKNOWN" ? "这条内容仍为未知，不能形成可执行条件。" : "系统暂不支持这类条件。"}原始内容继续保留。</p><Link className="button button-primary" href={next}>继续其他条件</Link></section>
      : saved && !reconsider || state.message ? <section className="guided-card" role="status"><h2>这条判断已保存</h2><p>{saved?.reason ?? reason}</p><Link className="button button-primary" href={next}>继续下一条</Link>{saved?.decision === "NEEDS_ADJUDICATION" ? <button className="guided-back" type="button" onClick={() => setReconsider(true)}>重新核对这条待处理条件</button> : null}</section>
        : <form className="guided-card" action={action} onReset={e => e.preventDefault()}><Hidden values={fields} />{row.evidence.map(e => <input key={e.evidence_ref_id} name="evidence_ref_id" type="hidden" value={e.evidence_ref_id} />)}
          <fieldset disabled={pending}>
            {deferred ? <><h2>记录为待处理，先继续其他项目</h2><Question title="哪一步无法确认？" name="problem" value={a.problem} onChange={change} choices={[["证据时间只有日期或不明确", "生效时间只有日期，或没有说明"], ["原文或岗位适用范围不清楚", "原文或岗位适用范围不清楚"], ["无法阅读原件或需要协助", "无法阅读原件，或需要协助"]]} /></>
              : question ? <><p className="field-help">证据问题 {questions.indexOf(question) + 1} / {questions.length}</p>
                {question.key.startsWith("time:") ? <><h2>{question.title}</h2><p>仅填原件明确给出的北京时间。只有日期时，请选下方“我现在无法判断”。</p>
                  <label>生效日期<input type="date" value={a[question.key.replace("time:", "date:")] ?? ""} onChange={e => change(question.key.replace("time:", "date:"), e.target.value)} /></label>
                  <label>生效时刻（北京时间）<input type="time" value={a[question.key.replace("time:", "clock:")] ?? ""} onChange={e => change(question.key.replace("time:", "clock:"), e.target.value)} /></label>
                  <button type="button" className="button button-primary" disabled={!a[question.key.replace("time:", "date:")] || !a[question.key.replace("time:", "clock:")]} onClick={() => change(question.key, "confirmed")}>时间已按原件填写</button>
                </> : <Question title={question.title} name={question.key} value={a[question.key]} choices={question.choices} onChange={change} />}
              </> : <Question title="最后确认：保存怎样的判断？" name="decision" value={a.decision} onChange={change} choices={[...(canApprove ? [["APPROVE", "这些证据支持该条件，确认采用"] as [string, string]] : []), ["REJECT", "该条件有误，不采用"]]} />}
            {(deferred || !question) ? <><label>补充说明（可选）<textarea value={a.note ?? ""} onChange={e => change("note", e.target.value)} maxLength={1400} /></label><p>{reason}</p><button type="submit" className="button button-primary" disabled={deferred ? !a.problem : !a.decision}>{pending ? "正在保存…" : "保存我的判断"}</button></> : null}
            {!deferred ? <button type="button" className="guided-back" onClick={() => change("defer", "yes")}>我现在无法判断</button> : null}
            <button type="button" className="guided-back" onClick={reset}>重新回答</button>
          </fieldset>{state.error ? <p role="alert" className="form-error">{state.error} 回答仍保留在当前窗口。</p> : null}
        </form>}
    <details className="guided-trace"><summary>查看技术追溯记录</summary><pre>{JSON.stringify({ preparation: prep.rule_preparation_id, payload: row.payload }, null, 2)}</pre></details>
  </div>;
}
