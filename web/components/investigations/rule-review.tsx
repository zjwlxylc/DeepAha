"use client";

import { useActionState, useState } from "react";
import { investigationRuleAction, type InvestigationActionState } from "../../app/review/investigations/actions";
import type { InvestigationFactPreparation, InvestigationRulePreparation, InvestigationTask } from "../../lib/investigations";
import { ruleAuthorities, ruleRelations, ruleApplicability, ruleDecisions } from "../../lib/investigation-rule-options";
import { EvidenceCheckDetail } from "./evidence-check";

const initial: InvestigationActionState = { error: null, message: null, taskId: null };
type RuleRow = InvestigationRulePreparation["rows"][number];

function conditionText(row: RuleRow): string {
  if (!row.payload) return "尚未形成拟规则";
  const fields: Record<string, string> = { education_level: "学历", major_code: "专业代码", hukou_region: "户籍", student_status: "在读／毕业状态", certificates: "证书", birth_date: "出生日期" };
  const operators: Record<string, string> = { GTE: "不低于", IN: "属于以下允许范围", CONTAINS_ALL: "需包含全部项目", BETWEEN: "位于以下区间" };
  const levels: Record<string, string> = { SECONDARY: "中等教育", ASSOCIATE: "专科", BACHELOR: "本科", MASTER: "硕士", DOCTORATE: "博士" };
  const value = row.payload.field === "education_level" && typeof row.payload.value === "string"
    ? levels[row.payload.value] ?? row.payload.value : JSON.stringify(row.payload.value);
  return `${fields[row.payload.field] ?? row.payload.field} ${operators[row.payload.operator] ?? row.payload.operator} ${value}`;
}

function Choice({ label, name, values }: { label: string; name: string; values: Record<string, string> }) {
  return <label>{label}<select name={name} defaultValue=""><option value="">请选择；未确认时可保留待裁决</option>
    {Object.entries(values).map(([value, text]) => <option value={value} key={value}>{text}</option>)}
  </select></label>;
}

function RuleForm({ task, facts, entityId, factSetId, preparation, row, requestKey }: {
  task: InvestigationTask; facts: InvestigationFactPreparation; entityId: string; factSetId: string;
  preparation?: InvestigationRulePreparation; row?: RuleRow; requestKey: string;
}) {
  const [formKey] = useState(requestKey);
  const [state, action, pending] = useActionState(investigationRuleAction, initial);
  return <form action={action} className="review-form" onReset={event => event.preventDefault()}>
    {Object.entries({ request_key: formKey, task_id: task.task_id, delivery_hash: task.delivery_hash ?? "",
      binding_id: facts.binding_id, check_id: facts.check_id, fact_preparation_id: facts.preparation_id,
      entity_id: entityId, fact_set_id: factSetId, kind: row ? "decision" : "prepare",
      rule_preparation_id: preparation?.rule_preparation_id ?? "", rule_candidate_id: row?.rule_candidate_id ?? "",
    }).map(([name, value]) => <input key={name} name={name} type="hidden" value={value} />)}
    <fieldset disabled={pending}><legend>{row ? "独立规则审核" : "从已保存事实整理规则"}</legend>
      {row ? <>
        <Choice label="规则决定" name="decision" values={ruleDecisions} />
        {row.evidence.map((evidence, index) => <fieldset key={evidence.evidence_ref_id}>
          <legend>证据 {index + 1} · 请核对上方原件与引用</legend>
          <input type="hidden" name="evidence_ref_id" value={evidence.evidence_ref_id} />
          <Choice label="证据权威级别" name={`authority:${evidence.evidence_ref_id}`} values={ruleAuthorities} />
          <Choice label="与拟规则的关系" name={`relation:${evidence.evidence_ref_id}`} values={ruleRelations} />
          <Choice label="是否适用于此目标" name={`applicability:${evidence.evidence_ref_id}`} values={ruleApplicability} />
          <label>证据生效时间（含时区）<input name={`effective_at:${evidence.evidence_ref_id}`} type="text" maxLength={40} placeholder="YYYY-MM-DDThh:mm:ss+08:00" /></label>
          <p>仅填写有依据的时间；只有日期或无法确认时留空并保留待裁决，不默认补为零点。</p>
          <label>证据判断依据<textarea name={`evidence_reason:${evidence.evidence_ref_id}`} required maxLength={2000} /></label>
        </fieldset>)}
        <label>规则审核依据<textarea name="reason" required maxLength={2000} /></label>
      </> : null}
      <button className="button button-primary" type="submit" disabled={pending}>{pending ? "正在记录…" : row ? "记录规则审核" : "整理规则候选"}</button>
    </fieldset>
    {state.error ? <p role="alert" className="form-error">{state.error}</p> : null}
    {state.message ? <p role="status">{state.message}</p> : null}
  </form>;
}

function RuleEvidence({ row, prep, task }: { row: RuleRow; prep: InvestigationRulePreparation; task: InvestigationTask }) {
  const source = prep.source_rows.find(source => source.candidate_id === row.candidate_id);
  return <>{row.evidence.map((evidence, index) => {
    const references = source?.evidence.filter(item => item.binding?.evidence_ref_id === evidence.evidence_ref_id) ?? [];
    return <div key={evidence.evidence_ref_id}>
      <h5>证据 {index + 1}</h5>
      {references.map((item, refIndex) => <div key={refIndex}>
        <blockquote>{item.reference.quote}</blockquote>
        <EvidenceCheckDetail evidence={item.reference} receipt={item.check_reference} />
        <p><a href={`/review/investigations/${encodeURIComponent(task.task_id)}/materials/${encodeURIComponent(item.reference.artifact_id)}`}>下载原件 · {item.reference.artifact_id}</a></p>
      </div>)}
      <details><summary>查看规则证据的完整原文与位置</summary><blockquote>{evidence.text}</blockquote>
        <pre className="investigation-json">{JSON.stringify(evidence.structural_locator, null, 2)}</pre>
      </details>
    </div>;
  })}</>;
}

export default function InvestigationRuleReview({ task, requestKey }: { task: InvestigationTask; requestKey: string }) {
  const facts = task.fact_review?.current;
  const ready = task.status === "APPROVED" && task.entity_binding?.bundle_status === "FROZEN"
    && !!facts && facts.binding_id === task.entity_binding.binding_id && facts.check_id === task.evidence_check?.check_id;
  const preparations = task.rule_review?.current ?? [];
  return <section className="human-test-panel" aria-labelledby="investigation-rule-review-title">
    <h2 id="investigation-rule-review-title">规则候选与独立审核</h2>
    <p>字段事实保存后，规则仍需独立审核。逐条批准不代表完整条件覆盖，尚不能据此给出完整资格结论。</p>
    {!facts || !ready ? <p>请先完成当前版本的字段审核并保存事实集；旧规则记录仅供追溯。</p> : facts.targets.map(target => {
      const saved = facts.promotions[target.entity_id], active = facts.active_fact_sets[target.entity_id];
      if (!saved || saved.status !== "ACTIVE" || saved.fact_set_id !== active?.fact_set_id) return null;
      const exists = preparations.some(p => p.fact_preparation_id === facts.preparation_id && p.fact_set_id === saved.fact_set_id && p.check_id === facts.check_id);
      return exists ? null : <div className="human-test-panel" key={target.entity_id}><h3>{target.name} · 独立规则审核</h3>
        <RuleForm task={task} facts={facts} entityId={target.entity_id} factSetId={saved.fact_set_id} requestKey={requestKey} />
      </div>;
    })}
    {preparations.map(prep => {
      const current = ready && prep.binding_id === facts.binding_id && prep.check_id === facts.check_id
        && prep.fact_preparation_id === facts.preparation_id && prep.fact_preparation_hash === facts.result_hash
        && prep.fact_set_id === facts.active_fact_sets[prep.entity_id]?.fact_set_id;
      return <article className="human-test-panel" key={prep.rule_preparation_id}>
        <h3>{prep.target.name} · {prep.target.target_scope === "UNIT" ? "岗位" : "公告"}规则候选</h3>
        {!current ? <p className="risk-note">此清单与当前核验或事实版本不一致，仅供查看。</p> : null}
        <p>全调查 {prep.source_rows.length} 个原始字段；此目标事实集 {prep.rows.length} 项，其中 {prep.rows.filter(r => r.rule_candidate_id).length} 项已形成拟规则。未知、不支持及未接入条件继续保留。</p>
        <details><summary>查看全部原始条件与待处理项</summary><ul>{prep.source_rows.map(source => <li key={source.source_index}>
          {task.binding_entities?.find(e => e.id === source.entity_id)?.name ?? source.entity_id} · {source.original_field}：{source.raw_value ?? "未披露"} · {source.original.status}
          {!source.candidate_id ? " · 尚未接入字段审核" : ""}{source.issue_codes.length ? " · 有待处理事项" : ""}
        </li>)}</ul></details>
        {prep.rows.map(row => {
          const source = prep.source_rows.find(source => source.candidate_id === row.candidate_id);
          const decision = row.rule_candidate_id ? prep.decisions[row.rule_candidate_id] : null;
          return <div className="human-test-panel" key={row.verified_fact_id}>
            <h4>{source?.original_field ?? row.field_name}</h4>
            <p>已保存事实：{row.fact_state === "UNKNOWN" ? "未知" : JSON.stringify(row.normalized_value)}</p>
            {!row.rule_candidate_id ? <p className="risk-note">{row.reason_code === "FACT_UNKNOWN" ? "事实保留未知，不能形成可执行规则。" : "当前不支持将此字段转为可执行规则，条件继续保留。"}</p> : <>
              <p>拟采用条件：{conditionText(row)}</p>
              <details><summary>查看拟规则表达式</summary><pre className="investigation-json">{JSON.stringify(row.payload, null, 2)}</pre></details>
            </>}
            <RuleEvidence row={row} prep={prep} task={task} />
            {decision ? <p>规则审核：{ruleDecisions[decision.decision as keyof typeof ruleDecisions] ?? decision.decision}。依据：{decision.reason}</p> : null}
            {current && row.rule_candidate_id && (!decision || decision.decision === "NEEDS_ADJUDICATION") ? <RuleForm
              key={`${row.rule_candidate_id}:${decision?.decision_id ?? "initial"}`} task={task} facts={facts} preparation={prep}
              row={row} entityId={prep.entity_id} factSetId={prep.fact_set_id} requestKey={requestKey} /> : null}
          </div>;
        })}
        {prep.decision_history.length ? <details><summary>历次规则审核与证据判断</summary>{prep.decision_history.map(record => <div key={record.decision_id}>
          <p>{record.created_at} · {ruleDecisions[record.decision as keyof typeof ruleDecisions]} · {record.reason} · 审核员 {record.reviewer_id}</p>
          <pre className="investigation-json">{JSON.stringify(record.evidence, null, 2)}</pre>
        </div>)}</details> : null}
        <details><summary>规则来源与版本</summary><p>{prep.compiler_version}</p><p className="investigation-hash">{prep.result_hash}</p>
          <p>事实集版本 {prep.fact_set_version} · {prep.fact_set_id}</p><p>来源包：{prep.source_bundle_revision_id}</p>
        </details>
      </article>;
    })}
    {task.rule_review?.history.length ? <details><summary>历次规则候选清单</summary><ul>{task.rule_review.history.map(p => <li key={p.rule_preparation_id}>{p.created_at} · {p.entity_id} · {p.compiler_version}</li>)}</ul></details> : null}
  </section>;
}
