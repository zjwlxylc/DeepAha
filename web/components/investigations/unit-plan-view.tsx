import Link from "next/link";
import type { InvestigationTask } from "../../lib/investigations";
import { currentSnapshotSource, type InvestigationUnitSnapshot } from "../../lib/unit-snapshots";
import { formatDateTime } from "../../lib/public-opportunities";
import { EvidenceCheckDetail } from "./evidence-check";
import { currentAnnouncementRules } from "../../lib/rule-applicability";
import { announcementPreviewPath } from "../../lib/announcement-snapshots";

const states: Record<string, string> = { KNOWN: "已保存事实", UNKNOWN: "调查后信息不足", CONFLICT: "材料冲突", UNSUPPORTED: "当前不支持处理", REJECTED: "已拒绝，仍待处理", UNLOCATED: "证据尚不能定位核验", UNPROCESSED: "尚未完成处理" };
const scopes = { UNIT: "本目标条件", ANNOUNCEMENT: "公告共同条件", EMPLOYER_GROUP: "所属单位共同条件" };

export default function UnitPlanView({ snapshot, task, embedded = false }: { snapshot: InvestigationUnitSnapshot; task: InvestigationTask; embedded?: boolean }) {
  const prep = currentSnapshotSource(snapshot, task);
  if (!prep) return <section className="human-test-panel" role="alert"><h2>快照关联版本已变化</h2><p>请返回任务重新核对当前证据、岗位归属和审核记录。</p></section>;
  const { plan, context } = snapshot;
  const counts = context.evidence_reference_counts;
  const name = task.binding_entities?.find(entity => entity.id === prep.entity_id)?.name ?? prep.target.name;
  const announcementRules = currentAnnouncementRules(task, snapshot);
  return <>
    <header className="human-test-hero"><div><p className="eyebrow">内部核对 · 条件与依据</p>{embedded ? <h2>{name} · 条件快照</h2> : <h1>{name} · 条件快照</h1>}<p>机会版本 {plan.target.opportunity_version} · 本目标版本 {plan.target.unit_version}</p><p>整理于 {formatDateTime(snapshot.created_at)}</p></div></header>
    <aside className="fixture-notice" aria-label="条件快照边界">完整适用范围与例外仍待审核，整体资格保持不确定。本页尚未进行个人资格判断。</aside>
    <section className="human-test-panel" aria-labelledby="unit-source-summary"><h2 id="unit-source-summary">本轮覆盖与证据状态</h2>
      <p>全调查共 {context.source_row_count} 个源字段：本快照保留 {plan.manifest.conditions.length} 项，另列 {context.excluded_source_rows.length} 项无关范围。</p>
      <p>全调查证据引用：通过 {counts.PASS} · 错误 {counts.FAIL} · 未核验 {counts.UNVERIFIED}。未核验单独保留。</p>
      <p>{plan.rules.length} 条规则具备独立批准记录；其余条件逐项保留，不能据此认定已覆盖全部资格要求。</p>
    </section>
    {!embedded ? <section className="human-test-panel" aria-labelledby="unit-announcement-applicability"><h2 id="unit-announcement-applicability">公告规则对本岗位的适用性</h2>
      <p>公告规则已有独立批准，是否适用于本岗位仍需另外审阅。适用性记录不改写本快照，也不解除整体资格的不确定状态。</p>
      {announcementRules.length ? <ul>{announcementRules.map(({ prep: source, row }) => <li key={row.rule_candidate_id}>
        来源公告：{source.target.name} · {source.source_rows.find(item => item.candidate_id === row.candidate_id)?.original_field ?? row.field_name} · <Link href={`/review/investigations/${encodeURIComponent(task.task_id)}/unit-plans/${encodeURIComponent(snapshot.plan_id)}/applicability/${encodeURIComponent(source.rule_preparation_id)}/${encodeURIComponent(row.rule_candidate_id!)}`}>审阅公告规则适用性</Link>
      </li>)}</ul> : <p>当前没有可审阅的已批准公告规则。请先完成公告级事实和独立规则审核。</p>}
      <p><Link href={announcementPreviewPath({ task_id: task.task_id, base_plan_id: snapshot.plan_id })} prefetch={false}>查看公告继承快照</Link> · 先查看当前来源与适用结果，再明确保存。</p>
    </section> : null}
    <section aria-labelledby="unit-conditions"><h2 id="unit-conditions">逐项条件与依据</h2>
      {plan.manifest.conditions.map(condition => {
        const source = prep.source_rows[condition.source_index];
        const disposition = plan.dispositions.find(d => d.condition_id === condition.condition_id);
        const admissions = plan.admissions.filter(a => disposition?.rule_ids.includes(a.rule_id));
        return <article className="human-test-panel" key={condition.condition_id}>
          <h3>{source.original_field}</h3><p>{scopes[condition.scope]} · {states[condition.state] ?? "状态待复核"}</p>
          <p>原始内容：{source.original.value ?? "未披露"}</p>
          {source.original.note ? <p className="risk-note">原始备注：{source.original.note}</p> : null}
          <p>{disposition?.kind === "RULE" ? "已有独立规则批准，仍需完整范围核对。" : "此项仍待处理，尚未认定为非资格条件。"}</p>
          {source.evidence.length ? source.evidence.map((item, index) => <div key={index}>
            <blockquote>{item.reference.quote}</blockquote>
            <EvidenceCheckDetail evidence={item.reference} receipt={item.check_reference} />
            <p><Link href={`/review/investigations/${encodeURIComponent(task.task_id)}/materials/${encodeURIComponent(item.reference.artifact_id)}`}>下载原件 · {item.reference.artifact_id}</Link></p>
          </div>) : <p>本项暂无可核验的证据引用。</p>}
          {admissions.map(admission => <details key={admission.rule_id}><summary>独立规则批准记录</summary>
            <p>审核员 {admission.reviewer_principal_id} · {formatDateTime(admission.reviewed_at)}</p>
            <p className="investigation-hash">决定标识：{admission.approval_decision_id}</p>
            {admission.evidence_validity.map(e => <p key={e.evidence_ref_id}>证据生效时间：{formatDateTime(e.valid_from)}；有效期终点：{e.valid_until ? formatDateTime(e.valid_until) : "尚未确定"}</p>)}
          </details>)}
        </article>;
      })}
    </section>
    {context.excluded_source_rows.length ? <section className="human-test-panel"><h2>无关范围的源字段</h2><p>这些字段属于其他岗位或单位，未借入本目标的规则。</p><ul>{context.excluded_source_rows.map(row => {
      const source = prep.source_rows[row.source_index];
      return <li key={row.source_index}>{task.binding_entities?.find(e => e.id === row.entity_id)?.name ?? row.entity_id} · {source.original_field}：{source.original.value ?? "未披露"}</li>;
    })}</ul></section> : null}
    <details className="human-test-panel"><summary>快照来源与版本</summary><dl className="compact-facts">
      <div><dt>规则准备</dt><dd className="investigation-hash">{context.rule_preparation_id}</dd></div>
      <div><dt>事实集</dt><dd>{context.fact_set_id} · 版本 {context.fact_set_version}</dd></div>
      <div><dt>岗位版本标识</dt><dd>{plan.target.unit_version_id}</dd></div>
      <div><dt>快照摘要</dt><dd className="investigation-hash">{snapshot.plan_hash}</dd></div>
      <div><dt>构造上下文摘要</dt><dd className="investigation-hash">{snapshot.context_hash}</dd></div>
      <div><dt>契约</dt><dd>{plan.contract_version} · {context.adapter_version}</dd></div>
    </dl></details>
  </>;
}
