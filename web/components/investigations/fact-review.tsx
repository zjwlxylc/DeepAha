"use client";

import { useActionState, useState } from "react";
import { investigationFactAction, type InvestigationActionState } from "../../app/review/investigations/actions";
import type { InvestigationFactPreparation, InvestigationTask } from "../../lib/investigations";

import { EvidenceCheckDetail } from "./evidence-check";

const initial: InvestigationActionState = { error: null, message: null, taskId: null };
const decisions: Record<string, string> = { APPROVE: "批准字段", REJECT: "拒绝候选", UNKNOWN: "保留未知", NEEDS_ADJUDICATION: "需要进一步裁决" };

function FactForm({ task, kind, preparation, candidate, entityId, requestKey }: { requestKey: string; task: InvestigationTask;
  kind: "prepare" | "decision" | "promote"; preparation?: InvestigationFactPreparation;
  candidate?: InvestigationFactPreparation["rows"][number]; entityId?: string }) {
  const [formKey] = useState(requestKey);
  const [state, action, pending] = useActionState(investigationFactAction, initial);
  return <form action={action} className="review-form" onReset={event => event.preventDefault()}>
    <input type="hidden" name="request_key" value={formKey} />
    <input type="hidden" name="check_id" value={preparation?.check_id ?? task.evidence_check?.check_id ?? ""} />
    <input type="hidden" name="task_id" value={task.task_id} />
    <input type="hidden" name="delivery_hash" value={task.delivery_hash ?? ""} />
    <input type="hidden" name="binding_id" value={task.entity_binding?.binding_id ?? ""} />
    <input type="hidden" name="kind" value={kind} />
    <input type="hidden" name="preparation_id" value={preparation?.preparation_id ?? ""} />
    <input type="hidden" name="candidate_id" value={candidate?.candidate_id ?? ""} />
    <input type="hidden" name="entity_id" value={entityId ?? ""} />
    <fieldset disabled={pending}>
      <legend>{kind === "decision" ? "独立字段审核" : kind === "promote" ? "保存此目标的审核事实集" : "准备字段候选"}</legend>
      {kind === "decision" ? <>
        <label>字段决定<select name="decision" required defaultValue=""><option value="">请选择</option>
          {Object.entries(decisions).filter(([value]) => candidate?.abstained ? value !== "APPROVE" : value !== "UNKNOWN")
            .map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label>原文是否支持该规范值<select name="evidence_support" required defaultValue="">
          <option value="">请核对原件与引用</option><option value="SUPPORTED">明确支持</option><option value="UNSUPPORTED">不支持</option><option value="UNKNOWN">尚不能确认</option>
        </select></label>
        <label>更正、适用范围与例外核查<select name="precedence_check" required defaultValue="">
          <option value="">请核对条件优先级</option><option value="PASSED">已核对，无未解决冲突</option><option value="FAILED">存在冲突</option><option value="UNKNOWN">尚不能确认</option>
        </select></label>
      </> : null}
      {kind === "promote" && entityId && preparation?.active_fact_sets[entityId] ? <>
        <p>此目标已有事实集，版本 {preparation.active_fact_sets[entityId].version}。</p>
        <details><summary>查看将被替代的事实集及来源</summary><p>{preparation.active_fact_sets[entityId].fact_set_id}</p><p>来源包：{preparation.active_fact_sets[entityId].source_bundle_revision_id}</p></details>
        <label className="investigation-check"><input name="supersedes_id" type="checkbox" required value={preparation.active_fact_sets[entityId].fact_set_id} />确认以本次审核结果替代该事实集，旧版本保留</label>
      </> : null}
      {kind !== "prepare" ? <label>本次审核依据<textarea name="reason" required maxLength={2000} /></label> : null}
      <button type="submit" className="button button-primary" disabled={pending}>{pending ? "正在记录…" : kind === "prepare" ? "整理字段候选与证据" : kind === "decision" ? "记录字段审核" : "保存审核事实集"}</button>
    </fieldset>
    {state.error ? <p role="alert" className="form-error">{state.error}</p> : null}
    {state.message ? <p role="status">{state.message}</p> : null}
  </form>;
}

function issueMessage(code: string): string {
  if (code.includes("UNBOUND")) return "目标尚未绑定正式身份";
  if (code.includes("GROUP_NOT_TARGETABLE")) return "单位分组条件保留，尚未确定适用岗位";
  if (code.includes("FIELD_UNSUPPORTED")) return "字段尚未支持规范化";
  if (code.includes("NORMALIZATION")) return "原文无法按当前规则确定规范值";
  if (code.includes("AMBIGUOUS")) return "引用有多处可能位置，需核对";
  if (code.includes("EVIDENCE")) return "引用未能精确定位，需核对原件";
  if (code.includes("VALUE")) return "缺少明确字段值";
  return "条件存在未知或冲突，保留待处理";
}

export default function InvestigationFactReview({ task, requestKey }: { task: InvestigationTask; requestKey: string }) {
  const preparation = task.fact_review?.current;
  const canPrepare = task.status === "APPROVED" && task.entity_binding?.bundle_status === "FROZEN" && !!task.evidence_check;
  const ready = canPrepare && preparation?.check_id === task.evidence_check?.check_id;
  const name = (entityId: string) => task.binding_entities?.find(e => e.id === entityId)?.name ?? entityId;
  return <section className="human-test-panel" aria-labelledby="investigation-field-review-title">
    <h2 id="investigation-field-review-title">候选字段与独立审核</h2>
    <p>请逐项确认“原文说了什么、适用于谁”。公告对所有岗位的共同要求、单位的要求和单个岗位的要求会分别保留；找到原文不代表已经理解正确。</p>
    {!preparation ? canPrepare ? <FactForm requestKey={requestKey} task={task} kind="prepare" /> : <p>完成内部材料审核、文档准备及身份归属后，可整理候选字段。</p> : <>
      {!ready && canPrepare ? <><p className="risk-note">当前核验回执已变化，旧清单保留供追溯。请先重新整理候选，再作出决定。</p><FactForm requestKey={requestKey} task={task} kind="prepare" /></> : null}
      <p>共 {preparation.rows.length} 个原始字段；{preparation.rows.filter(r => r.candidate_id).length} 个已接入审核，{preparation.rows.filter(r => !r.candidate_id).length} 个仍待处理。未知字段与未接入条件不会因保存事实集而消失。</p>
      {preparation.rows.map(row => {
        const decision = row.candidate_id ? preparation.decisions[row.candidate_id] : null;
        return <details className="review-condition-details" key={row.source_index} open={preparation.rows.length <= 6}>
          <summary>{name(row.entity_id)} · {row.original_field} · {decision ? decisions[decision.decision] ?? "已记录" : "等待核对"}</summary>
          <article>
          <h3>{name(row.entity_id)} · {row.original_field}</h3>
          <p>原始候选：{row.raw_value ?? "未披露"}</p>
          <p>原始调查状态：{row.original.status}；规范候选：{!row.candidate_id ? "尚未接入审核，保留原始状态与待处理原因" : row.abstained ? "未知，保留原文待核对" : JSON.stringify(row.normalized_value_candidate)}</p>
          {row.original.note ? <p>调查备注：{row.original.note}</p> : null}
          {row.issue_codes.length ? <ul>{Array.from(new Set(row.issue_codes.map(issueMessage))).map(issue => <li key={issue}>{issue}</li>)}</ul> : null}
          {row.evidence.map((evidence, index) => <div key={index}>
            <blockquote>{evidence.reference.quote}</blockquote>
            <EvidenceCheckDetail evidence={evidence.reference} receipt={evidence.check_reference} />
            <p><a href={`/review/investigations/${encodeURIComponent(task.task_id)}/materials/${encodeURIComponent(evidence.reference.artifact_id)}`}>下载原件 · {evidence.reference.artifact_id}</a> · 网址由调查服务声明，需结合原件核对。</p>
            {evidence.binding ? <details><summary>查看准确位置和完整证据块</summary>
              <pre className="investigation-json">{JSON.stringify(evidence.binding.structural_locator, null, 2)}</pre>
              <blockquote>{evidence.binding.block_text}</blockquote>
            </details> : <p>尚未找到唯一、准确的文档位置。</p>}
          </div>)}
          {decision ? <p>审核：{decisions[decision.decision] ?? decision.decision}。依据：{decision.reason}</p> : null}
          {row.candidate_id && ready && (!decision || decision.decision === "NEEDS_ADJUDICATION") ?
            <FactForm key={`${row.candidate_id}:${decision?.decision_id ?? "initial"}`} requestKey={requestKey} task={task} kind="decision" preparation={preparation} candidate={row} /> : null}
        </article></details>;
      })}
      {preparation.targets.filter(t => t.extraction_run_id).map(target => {
        const promotion = preparation.promotions[target.entity_id];
        const targetRows = preparation.rows.filter(row => row.entity_id === target.entity_id && row.candidate_id);
        const targetDecisions = targetRows.map(row => preparation.decisions[row.candidate_id!]?.decision);
        const canSave = targetDecisions.length > 0 && targetDecisions.every(value => value && value !== "NEEDS_ADJUDICATION")
          && targetDecisions.some(value => value === "APPROVE" || value === "UNKNOWN");
        return <div className="human-test-panel" key={target.entity_id}>
          <h3>{target.name} · {target.target_scope === "UNIT" ? "岗位" : "公告"}事实集</h3>
          {promotion ? <><p>已保存审核事实集，状态：{promotion.status}。{promotion.reason}；尚不代表完整资格判断。</p><details><summary>查看事实集标识</summary><p>{promotion.fact_set_id}</p></details></>
            : ready && canSave ? <FactForm requestKey={requestKey} task={task} kind="promote" preparation={preparation} entityId={target.entity_id} />
              : <p>请先完成此目标的逐字段决定并处理待裁决项；至少有一项被批准或明确保留未知，才能保存审核事实集。</p>}
        </div>;
      })}
      <details><summary>字段映射与审核版本</summary><p>{preparation.mapping_version}</p><p className="investigation-hash">{preparation.result_hash}</p></details>
    </>}
    {(task.fact_review?.history.length ?? 0) > 1 ? <details><summary>历次候选清单记录</summary><ul>{task.fact_review?.history.map(p => <li key={p.preparation_id}>{p.created_at} · {p.mapping_version} · 归属记录 {p.binding_id}</li>)}</ul><p>旧归属的审核决定不会自动应用到当前目标。</p></details> : null}
  </section>;
}
