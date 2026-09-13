"use client";

import { useActionState, useState } from "react";
import type { InvestigationBindingTarget, InvestigationTask } from "../../lib/investigations";
import { bindInvestigationAction } from "../../app/review/investigations/actions";
import { selectedPositions } from "../../lib/guided-review";
import { Hidden } from "./guided-controls";

export default function GuidedExisting({ task, ids, targets, requestKey }: { task: InvestigationTask; ids: string[]; targets: InvestigationBindingTarget[]; requestKey: string }) {
  const [state, action, pending] = useActionState(bindInvestigationAction, { error: null, message: null, taskId: null });
  const [selected, setSelected] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const previous = task.entity_binding;
  const choices = previous ? targets.filter(t => t.opportunity_id === previous.opportunity_id && t.version === previous.opportunity_version) : targets;
  const target = choices.find(t => `${t.opportunity_id}/${t.version}` === selected);
  const positions = selectedPositions(task, ids).filter(p => !previous?.positions.some(old => old.entity_id === p.id));
  const retained = Object.fromEntries((previous?.positions ?? []).map(p => [`position:${p.entity_id}`, `${p.opportunity_unit_id}/${p.opportunity_unit_version_id}`]));
  const newCount = positions.filter(p => answers[p.id] === "new").length;
  return <section aria-labelledby="guided-existing-title"><h2 id="guided-existing-title">使用已有公告，继续核对这两个岗位</h2>
    <p>这一步只确认当前材料属于哪份公告、哪些岗位。以前的记录保留；不会把以前的审核结论自动算作本次核对结果。</p>
    {!choices.length ? <p role="alert">当前没有可选择的记录，或原记录版本已变化。请保留当前页面，由维护人员核查已有记录；反复点击新建不能解决此问题。</p> : <form action={action} className="review-form">
      <Hidden values={{ task_id: task.task_id, delivery_hash: task.delivery_hash, previous_binding_id: previous?.binding_id, request_key: requestKey, ...retained }} />
      <fieldset disabled={pending}>
        <label>选择已有公告<select name="target" required value={selected} onChange={e => { setSelected(e.target.value); setAnswers({}); }}><option value="">请选择并对照当前官方公告</option>{choices.map(t => <option key={t.opportunity_id} value={`${t.opportunity_id}/${t.version}`}>{t.title} · 第 {t.version} 版</option>)}</select></label>
        {target ? <><p>已选公告：{target.title}</p><details><summary>查看记录编号</summary><p>{target.public_id} · 第 {target.version} 版</p></details>
          {positions.map(p => <label key={p.id}>{p.name}（{p.code ?? "无编号"}）对应哪条已有岗位？
            <select required value={answers[p.id] ?? ""} onChange={e => setAnswers({ ...answers, [p.id]: e.target.value })}>
              <option value="">请对照单位、岗位名称和编号选择</option>
              {target.positions.filter(u => !previous?.positions.some(old => old.opportunity_unit_id === u.unit_id)).map(u => <option key={u.unit_id} value={`${u.unit_id}/${u.version_id}`} disabled={Object.entries(answers).some(([id, value]) => id !== p.id && value === `${u.unit_id}/${u.version_id}`)}>{u.label} · 编号 {u.key}</option>)}
              <option value="new">已核对，列表中没有这个岗位（下一步登记）</option>
            </select>
            {answers[p.id] && answers[p.id] !== "new" ? <input type="hidden" name={`position:${p.id}`} value={answers[p.id]} /> : null}
          </label>)}
          {newCount ? <p>有 {newCount} 个岗位尚未登记。先确认已有公告，下一步再确认并保存这些岗位。</p> : null}
        </> : null}
        <label>你核对了原件哪里？<input name="reason" required maxLength={2000} placeholder="例如：同一份官方公告，岗位表名称和编号一致" /></label>
        <label className="guided-position"><input type="checkbox" required />我已对照原件，确认所选公告及岗位对应正确</label>
        <button type="submit" className="button button-primary" disabled={!target || positions.some(p => !answers[p.id])}>{pending ? "正在保存…" : "确认使用已有记录，继续"}</button>
      </fieldset>
      {state.error ? <p role="alert">{state.error}</p> : null}{state.message ? <p role="status">已保存，正在进入下一步。</p> : null}
    </form>}
  </section>;
}
