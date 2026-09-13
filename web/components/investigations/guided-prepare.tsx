"use client";

import { useActionState, useEffect, useState } from "react";
import type { InvestigationTask } from "../../lib/investigations";
import { investigationFactAction, investigationRuleAction } from "../../app/review/investigations/actions";
import { Hidden } from "./guided-controls";

export function PreparationProgress() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return <aside className="guided-limits">
    <p role="status">正在等待准备结果，完成后会自动显示下一步。</p>
    <p>已等待 {seconds} 秒。材料较多时可能需要数分钟，请勿重复提交。</p>
    {seconds >= 15 ? <><p>如果页面长时间没有变化，可以重新读取已保存结果。此操作只查看结果，不会重复发起准备；若仍显示准备入口，说明暂未读取到完成结果。</p><button type="button" className="button button-secondary" onClick={() => window.location.assign(window.location.pathname + window.location.search)}>重新读取已保存结果</button></> : null}
  </aside>;
}

export default function GuidedPrepare({ task, kind, requestKey }: { task: InvestigationTask; kind: "prepare" | "promote" | "rules"; requestKey: string }) {
  const [state, action, pending] = useActionState(kind === "rules" ? investigationRuleAction : investigationFactAction, { error: null, message: null, taskId: null });
  const [key] = useState(requestKey);
  const prep = task.fact_review?.current, entity = task.workbench?.entity_id ?? "";
  const active = prep?.active_fact_sets[entity];
  return <section className="guided-card"><h2>{kind === "prepare" ? "岗位已选好，准备要核对的内容" : kind === "promote" ? "这些回答已经逐条保存" : "接下来核对判断条件"}</h2>
    <p>{kind === "prepare" ? "系统将已有原件整理成一条条问题，不会替你作出判断。" : kind === "promote" ? "继续前，将已审核内容归入当前岗位的记录。未知和未接入内容会继续保留。" : "系统根据已保存内容准备判断条件。每条条件还需要你单独核对，不能自动批准。"}</p>
    {kind === "prepare" ? <p>首次准备会核验这份公告的整份材料，不只当前岗位。材料较多时可能需要数分钟，完成后显示第一条内容。</p> : null}
    <form action={action} onReset={e => e.preventDefault()}><Hidden values={{ task_id: task.task_id, delivery_hash: task.delivery_hash, binding_id: task.entity_binding?.binding_id, check_id: kind === "prepare" ? task.evidence_check?.check_id : prep?.check_id,
      kind: kind === "rules" ? "prepare" : kind, request_key: key, workbench: "1", preparation_id: prep?.preparation_id, fact_preparation_id: prep?.preparation_id,
      entity_id: entity, fact_set_id: prep?.promotions[entity]?.fact_set_id, reason: "本人确认将当前逐条审核结果归入此岗位，未知及未接入内容继续保留。" }} />
      {kind === "promote" && active ? <label className="guided-position"><input type="checkbox" required name="supersedes_id" value={active.fact_set_id} />以本次回答更新该岗位的记录，保留旧版本</label> : null}
      <button className="button button-primary" disabled={pending}>{pending ? "正在准备…" : kind === "prepare" ? "准备核对内容" : kind === "promote" ? "归入岗位记录，继续" : "准备判断条件"}</button>
      {pending ? <PreparationProgress /> : null}
      {state.error ? <p role="alert">{state.error}</p> : null}{state.message ? <p role="status">已保存，正在回读下一步。</p> : null}
    </form>
  </section>;
}
