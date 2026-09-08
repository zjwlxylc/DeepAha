"use client";

import { useActionState, useState } from "react";
import { registerInvestigationIdentityAction, type InvestigationActionState } from "../../app/review/investigations/actions";
import type { InvestigationTask } from "../../lib/investigations";

const initial: InvestigationActionState = { error: null, message: null, taskId: null };
const types = [
  ["PUBLIC_INSTITUTION_JOB", "事业单位招聘"], ["STATE_OWNED_ENTERPRISE_JOB", "国央企招聘"],
  ["CIVIL_SERVICE", "公务员招录"], ["GRASSROOTS_PROGRAM", "基层服务项目"],
  ["YOUTH_POLICY_BENEFIT", "青年政策权益"], ["COMPETITION", "比赛"],
  ["RESEARCH_PROGRAM", "科研计划"], ["SCHOLARSHIP", "奖学金"],
  ["YOUTH_DEVELOPMENT_PROGRAM", "青年成长计划"],
];

export default function InvestigationIdentityForm({ task, requestKey }: { task: InvestigationTask; requestKey: string }) {
  const [formKey] = useState(requestKey);
  const [state, action, pending] = useActionState(registerInvestigationIdentityAction, initial);
  const [selected, setSelected] = useState<string[]>([]);
  const binding = task.entity_binding;
  const positions = (task.binding_entities ?? []).filter(e => e.kind === "position"
    && !binding?.positions.some(p => p.entity_id === e.id));
  const announcement = task.binding_entities?.find(e => e.kind === "announcement");
  if (binding && positions.length === 0) return null;
  return <details><summary>{binding ? "登记尚无身份的岗位" : "首次登记新机会"}</summary>
    <p>登记只建立内部身份，内容保持待核验。请核对官方原件；已有机会或岗位应使用关联入口。</p>
    <form action={action} className="review-form" onReset={event => event.preventDefault()}>
      <input type="hidden" name="request_key" value={formKey} />
      <input type="hidden" name="task_id" value={task.task_id} />
      <input type="hidden" name="delivery_hash" value={task.delivery_hash ?? ""} />
      <input type="hidden" name="previous_binding_id" value={binding?.binding_id ?? ""} />
      {!binding ? <fieldset disabled={pending}><legend>机会身份</legend>
        <label>机会名称<input name="canonical_title" required maxLength={500} defaultValue={announcement?.name ?? ""} /></label>
        <label>机会类别<select name="type" required defaultValue="">
          <option value="">请依据公告选择类别</option>
          {types.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label>官方发布单位<input name="issuer_name" required maxLength={500} /></label>
      </fieldset> : null}
      {positions.length ? <fieldset disabled={pending}><legend>登记岗位</legend>
        <p>只勾选需要新建身份的岗位。单位分组不会被登记为岗位；未选择项保持待关联。</p>
        {positions.map(position => <div key={position.id}>
          <label className="investigation-check"><input type="checkbox" name="new_position" value={position.id} checked={selected.includes(position.id)}
            onChange={e => setSelected(e.target.checked ? [...selected, position.id] : selected.filter(id => id !== position.id))} />{position.name}</label>
          {selected.includes(position.id) ? <>
            <label>岗位名称<input name={`label:${position.id}`} required maxLength={500} defaultValue={position.name} /></label>
            <label>内部识别键（有官方编号时用编号）<input name={`unit_key:${position.id}`} required maxLength={256} defaultValue={position.code ?? ""} /></label>
          </> : null}
        </div>)}
      </fieldset> : null}
      <label>登记核对依据<textarea name="reason" required maxLength={2000} disabled={pending} /></label>
      <button type="submit" className="button button-primary" disabled={pending || !!binding && selected.length === 0}>
        {pending ? "正在登记…" : binding ? "登记岗位并保留已有归属" : "登记内部机会并关联材料"}
      </button>
      {state.error ? <p role="alert" className="form-error">{state.error}</p> : null}
      {state.message ? <p role="status">{state.message}</p> : null}
    </form>
  </details>;
}
