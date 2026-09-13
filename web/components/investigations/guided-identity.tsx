"use client";

import { useActionState, useState } from "react";
import Link from "next/link";
import type { InvestigationTask } from "../../lib/investigations";
import { registerInvestigationIdentityAction } from "../../app/review/investigations/actions";
import { selectedPositions } from "../../lib/guided-review";

export default function GuidedIdentity({ task, ids, requestKey }: { task: InvestigationTask; ids: string[]; requestKey: string }) {
  const [state, action, pending] = useActionState(registerInvestigationIdentityAction, { error: null, message: null, taskId: null });
  const [key] = useState(requestKey);
  const positions = selectedPositions(task, ids).filter(e => !task.entity_binding?.positions.some(p => p.entity_id === e.id));
  const units = (task.opportunities?.units ?? []) as { name: string; positions: { id: string }[] }[];
  return <section className="guided-card"><p className="eyebrow">第 2 步，共 3 步 · 确认选对岗位</p>
    <h1>这两个岗位与原件一致吗？</h1>
    <p>先核对名称、单位和编号。已有岗位关联会保留；这一步只记录你选择的对象。</p>
    <div className="guided-source-links"><a href={task.notice_url} target="_blank" rel="noreferrer">打开官方公告 ↗</a>{task.materials.map((m, i) => <a key={m.artifact_id} href={`/review/investigations/${task.task_id}/materials/${encodeURIComponent(m.artifact_id)}`}>打开附件 {i + 1}</a>)}</div>
    <form action={action} className="review-form" onReset={e => e.preventDefault()}>
      <input type="hidden" name="request_key" value={key} /><input type="hidden" name="task_id" value={task.task_id} /><input type="hidden" name="delivery_hash" value={task.delivery_hash ?? ""} /><input type="hidden" name="previous_binding_id" value={task.entity_binding?.binding_id ?? ""} />
      <fieldset disabled={pending}>
        {!task.entity_binding ? <details open><summary>公告名称与发布单位 · 请对照原件</summary>
          <label>公告名称<input name="canonical_title" defaultValue={String(task.opportunities?.opportunity_name ?? "")} required maxLength={500} /></label>
          <label>发布单位<input name="issuer_name" defaultValue={String(task.opportunities?.publish_unit ?? "")} required maxLength={500} /></label>
          <label>这是什么类型的机会？<select name="type" required defaultValue=""><option value="">请按公告选择</option><option value="PUBLIC_INSTITUTION_JOB">事业单位招聘</option><option value="STATE_OWNED_ENTERPRISE_JOB">国央企招聘</option><option value="CIVIL_SERVICE">公务员招录</option><option value="GRASSROOTS_PROGRAM">基层服务项目</option><option value="YOUTH_POLICY_BENEFIT">青年政策权益</option><option value="COMPETITION">比赛</option><option value="RESEARCH_PROGRAM">科研计划</option><option value="SCHOLARSHIP">奖学金</option><option value="YOUTH_DEVELOPMENT_PROGRAM">青年成长计划</option></select></label>
        </details> : null}
        {positions.map(p => <div key={p.id} className="guided-identity-row"><h2>{units.find(u => u.positions.some(row => row.id === p.id))?.name ?? "单位待核对"}</h2>
          <input type="hidden" name="new_position" value={p.id} />
          <label>岗位名称<input name={`label:${p.id}`} defaultValue={p.name} required maxLength={500} /></label>
          <label>岗位编号<input name={`unit_key:${p.id}`} defaultValue={p.code ?? ""} required maxLength={256} /></label>
          {!p.code ? <p>原件没有编号时先暂停，不需要你编造编号。请在反馈中指出该岗位。</p> : null}
        </div>)}
        <label>你核对了原件哪里？<input name="reason" required maxLength={2000} placeholder="例如：岗位表第 5 行和第 8 行的单位、名称、编号" /></label>
        <label className="guided-position"><input type="checkbox" required />我已对照原件，确认这些单位、岗位名称和编号对应正确</label>
        <button className="button button-primary" type="submit">{pending ? "正在保存…" : "确认这两个岗位，开始逐条核对"}</button>
      </fieldset>
      {state.error ? <p role="alert">{state.error} <Link href={`/review/investigations/${task.task_id}#investigation-binding-title`}>已有对象的关联与人工处理</Link></p> : null}
      {state.message ? <p role="status">已保存岗位选择，正在回读。</p> : null}
    </form>
  </section>;
}
