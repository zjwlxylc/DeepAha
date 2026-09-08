"use client";

import { useActionState, useState } from "react";
import { bindInvestigationAction, type InvestigationActionState } from "../../app/review/investigations/actions";
import type { InvestigationBindingTarget, InvestigationTask } from "../../lib/investigations";

const initial: InvestigationActionState = { error: null, message: null, taskId: null };

export default function InvestigationBindingForm({ task, targets, requestKey }: { task: InvestigationTask; targets: InvestigationBindingTarget[]; requestKey: string }) {
  const [formKey] = useState(requestKey);
  const [selected, setSelected] = useState("");
  const [state, action, pending] = useActionState(bindInvestigationAction, initial);
  const target = targets.find(t => `${t.opportunity_id}/${t.version}` === selected);
  const positions = task.binding_entities?.filter(e => e.kind === "position") ?? [];
  return <form action={action} className="review-form" onReset={event => event.preventDefault()}>
    <input type="hidden" name="request_key" value={formKey} />
    <input type="hidden" name="task_id" value={task.task_id} />
    <input type="hidden" name="delivery_hash" value={task.delivery_hash ?? ""} />
    <input type="hidden" name="previous_binding_id" value={task.entity_binding?.binding_id ?? ""} />
    <label>关联到已有机会
      <select name="target" required value={selected} onChange={e => setSelected(e.target.value)} disabled={pending}>
        <option value="">请选择并核对机会身份</option>
        {targets.map(t => <option key={t.opportunity_id} value={`${t.opportunity_id}/${t.version}`}>{t.title} · 版本 {t.version} · {t.public_id}</option>)}
      </select>
    </label>
    {target ? <fieldset key={selected} disabled={pending}><legend>逐项关联岗位</legend>
      <p>未选择的岗位保持待关联。调查中的发布单位分组保留原样，不作为岗位身份。</p>
      {positions.map(p => <label key={p.id}>{p.name}{p.code ? `（${p.code}）` : ""}
        <select name={`position:${p.id}`} defaultValue="">
          <option value="">暂不关联</option>
          {target.positions.map(unit => <option key={unit.unit_id} value={`${unit.unit_id}/${unit.version_id}`}>{unit.label} · {unit.key} · {unit.public_id}</option>)}
        </select>
      </label>)}
      {!positions.length ? <p>此调查没有可关联的岗位子项。</p> : null}
    </fieldset> : null}
    {task.entity_binding ? <p>本次提交将替代当前归属方案。请重新选择本次要保留的全部岗位关联；历史记录会保留。</p> : null}
    <label>归属核对依据<textarea name="reason" required maxLength={2000} disabled={pending} /></label>
    <button className="button button-primary" type="submit" disabled={pending || !target}>{pending ? "正在记录归属…" : "确认归属并冻结来源"}</button>
    {state.error ? <p role="alert" className="form-error">{state.error}</p> : null}
    {state.message ? <p role="status">{state.message}</p> : null}
  </form>;
}
