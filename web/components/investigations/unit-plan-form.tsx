"use client";

import Link from "next/link";
import { useActionState, useState } from "react";
import { prepareUnitPlanAction, type UnitPlanActionState } from "../../app/review/investigations/unit-plan-actions";
import type { InvestigationRulePreparation, InvestigationTask } from "../../lib/investigations";

const initial: UnitPlanActionState = { error: null, planId: null };

export default function UnitPlanForm({ task, prep, requestKey }: { task: InvestigationTask; prep: InvestigationRulePreparation; requestKey: string }) {
  const [key] = useState(requestKey);
  const [state, action, pending] = useActionState(prepareUnitPlanAction, initial);
  const unresolved = prep.rows.some(row => row.rule_candidate_id && !["APPROVE", "REJECT"].includes(prep.decisions[row.rule_candidate_id]?.decision));
  if (prep.target.target_scope !== "UNIT") return null;
  if (unresolved) return <p>本目标仍有规则待决定，完成逐条裁决后可整理条件快照。</p>;
  return <form action={action} className="review-form" onReset={event => event.preventDefault()}>
    {Object.entries({ request_key: key, task_id: task.task_id, delivery_hash: prep.delivery_hash,
      binding_id: prep.binding_id, check_id: prep.check_id, fact_preparation_id: prep.fact_preparation_id,
      entity_id: prep.entity_id, fact_set_id: prep.fact_set_id, rule_preparation_id: prep.rule_preparation_id,
    }).map(([name, value]) => <input key={name} name={name} type="hidden" value={value} />)}
    <p>汇总本目标的条件、依据及待审事项。完整适用范围和整体资格仍待判断。</p>
    <button className="button button-primary" type="submit" disabled={pending}>{pending ? "正在核对当前证据…" : "整理条件快照"}</button>
    {state.error ? <p role="alert" className="form-error">{state.error}</p> : null}
    {state.planId ? <p role="status">条件快照已准备。<Link href={`/review/investigations/${encodeURIComponent(task.task_id)}/unit-plans/${encodeURIComponent(state.planId)}`}>查看条件快照</Link></p> : null}
  </form>;
}
