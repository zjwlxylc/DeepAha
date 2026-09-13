"use client";

import { useActionState, useState } from "react";
import Link from "next/link";
import type { InvestigationTask } from "../../lib/investigations";
import { investigationFactAction } from "../../app/review/investigations/actions";
import { factAnswer, readableLocator, readableValue } from "../../lib/guided-review";
import { Hidden, Question, useGuidedAnswers } from "./guided-controls";

export default function GuidedFact({ task, requestKey, next }: { task: InvestigationTask; requestKey: string; next: string }) {
  const prep = task.fact_review!.current!, row = prep.rows[0];
  const [state, action, pending] = useActionState(investigationFactAction, { error: null, message: null, taskId: null });
  const saved = row?.candidate_id ? prep.decisions[row.candidate_id] : null;
  const [reconsider, setReconsider] = useState(false);
  const { answers: a, change, reset, requestKey: key } = useGuidedAnswers(task.draft_scope ? JSON.stringify(["guided-fact", task.draft_scope, task.task_id, task.delivery_hash, prep.binding_id, prep.preparation_id, row?.candidate_id, saved?.decision_id]) : null, requestKey, !!state.message);
  if (!row) return <p>这一页没有内容，请返回上一条。</p>;
  const answer = factAnswer(a.support ?? "", a.scope ?? "", row.abstained);
  const reason = `本人回答：原文${a.support === "yes" ? "支持显示内容" : a.support === "no" ? "不支持显示内容" : "尚不能确认"}；适用范围及更正${a.scope === "clear" ? "已核对无未决冲突" : "尚不能确认"}。${a.problem ? `待处理原因：${a.problem}。` : ""}${a.note ?? ""}`;
  const terminal = !!saved && !reconsider;
  return <div className="guided-question-layout">
    <div className="guided-comparison">
      <section className="guided-source"><h2>原件怎么写</h2>
        {row.evidence.length ? row.evidence.map((e, i) => <div key={i}><p className="field-help">{readableLocator(e.reference.locator)}</p><blockquote>{e.binding?.block_text ?? e.reference.quote}</blockquote>
          {!e.binding ? <p className="form-error">这段引用还没有准确定位，无法确认时请标记待处理。</p> : null}
          <a href={`/review/investigations/${task.task_id}/materials/${encodeURIComponent(e.reference.artifact_id)}`}>打开对应原件</a></div>) : <p>没有可供核对的原文。此项应保留待处理。</p>}
      </section>
      <section className="guided-proposal"><p className="eyebrow">需要你核对</p><h2>{row.original_field}</h2><p className="guided-value">{row.abstained ? "暂不能形成可靠解释，请结合原文核对" : readableValue(row.normalized_value_candidate)}</p>
        {row.abstained ? <p>可能是证据、适用范围或系统解析能力不足，不能据此认定原文没有要求。</p> : null}
        <p>系统原始摘录：{row.raw_value ?? "未披露"}</p>{row.original.note ? <p>{row.original.note}</p> : null}
      </section>
    </div>
    {terminal || state.message ? <section className="guided-card" role="status"><h2>这条判断已保存</h2><p>{saved?.reason ?? reason}</p><Link className="button button-primary" href={next}>继续下一条</Link>{saved?.decision === "NEEDS_ADJUDICATION" ? <button className="guided-back" type="button" onClick={() => setReconsider(true)}>重新核对这条待处理内容</button> : null}</section>
      : !row.candidate_id ? <section className="guided-card"><h2>这条内容还不能直接审核</h2><p>系统尚不能处理这类内容，已保留在待处理范围中。你可以继续核对其他内容。</p><Link className="button button-primary" href={next}>继续其他内容</Link></section>
        : <form action={action} className="guided-card" onReset={e => e.preventDefault()}>
          <Hidden values={{ task_id: task.task_id, delivery_hash: task.delivery_hash, binding_id: prep.binding_id, check_id: prep.check_id, preparation_id: prep.preparation_id, candidate_id: row.candidate_id, kind: "decision", workbench: "1", request_key: key, ...answer, reason }} />
          {saved ? <p>此前已标记待处理：{saved.reason}</p> : null}
          <fieldset disabled={pending}>
            {!a.support ? <Question title={row.abstained ? "对照原件，这项内容目前应保留为未知吗？" : "对照原件，这条内容表达正确吗？"} name="support" value={a.support} onChange={change} choices={[["yes", row.abstained ? "对，目前仍不能确定" : "是，原文支持这条内容"], ["no", "不对，与原文不一致"], ["unsure", "我现在无法判断"]]} />
              : a.support === "yes" && !a.scope ? <Question title="这条要求适用于当前岗位吗？" name="scope" value={a.scope} onChange={change} choices={[["clear", "已核对岗位、共同条件及更正，没有未解决冲突"], ["uncertain", "适用范围、更正或例外还不清楚"]]} />
                : <>
                  <h2>{answer?.decision === "APPROVE" ? "保存为：已确认" : answer?.decision === "UNKNOWN" ? "保存为：保留未知" : answer?.decision === "REJECT" ? "保存为：内容有误" : "保存为：待处理"}</h2>
                  {answer?.decision === "NEEDS_ADJUDICATION" ? <Question title="哪里让你无法判断？" name="problem" value={a.problem} onChange={change} choices={[["原件打不开", "原件打不开"], ["原文或适用范围不清楚", "原文或适用范围不清楚"], ["需要别人协助", "看不懂，需要协助"], ["稍后再核对", "稍后再核对"]]} /> : null}
                  <p>{reason}</p><label>补充说明（可选）<textarea value={a.note ?? ""} onChange={e => change("note", e.target.value)} maxLength={1400} /></label>
                  <button className="button button-primary" type="submit" disabled={!answer || answer.decision === "NEEDS_ADJUDICATION" && !a.problem}>{pending ? "正在保存…" : "保存我的判断"}</button>
                </>}
            {a.support ? <button className="guided-back" type="button" onClick={reset}>重新回答</button> : null}
          </fieldset>
          {state.error ? <p role="alert" className="form-error">{state.error} 你的回答仍保留在当前窗口。</p> : null}
        </form>}
    <details className="guided-trace"><summary>查看技术追溯记录</summary><pre>{JSON.stringify({ preparation: prep.preparation_id, issues: row.issue_codes, evidence: row.evidence.map(e => e.check_reference) }, null, 2)}</pre></details>
  </div>;
}
