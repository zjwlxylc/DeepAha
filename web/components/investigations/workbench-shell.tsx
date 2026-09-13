import Link from "next/link";
import { randomUUID } from "node:crypto";
import type { InvestigationBindingTarget, InvestigationTask } from "../../lib/investigations";
import InvestigationBindings from "./bindings";
import InvestigationFactReview from "./fact-review";
import InvestigationRuleReview from "./rule-review";
import InvestigationEvidence from "./evidence";
import { formatDateTime } from "../../lib/public-opportunities";

export default function WorkbenchShell({ task, step, queue, targets }: {
  task: InvestigationTask; step: string; queue: string; targets: InvestigationBindingTarget[];
}) {
  const entityId = task.workbench?.entity_id;
  const offset = task.workbench?.offset ?? 0;
  const selected = task.binding_entities?.find(entity => entity.id === entityId);
  const units = (task.opportunities?.units ?? []) as { id: string; name: string; positions: { id: string; name: string; code?: string }[] }[];
  const unit = units.find(value => value.id === entityId || value.positions.some(position => position.id === entityId));
  const slice = task.fact_review?.current?.slice;
  const total = step === "rules" ? (task.rule_review?.current[0]?.slice?.total ?? 0)
    : (task.fact_review?.current?.slice?.total ?? task.workbench?.total ?? 0);
  const href = (nextStep: string, entity = entityId, nextOffset = 0) => {
    const query = new URLSearchParams({ step: nextStep });
    if (entity) query.set("entity_id", entity);
    if (nextOffset) query.set("offset", String(nextOffset));
    if (queue) query.set("queue", queue);
    return `/review/investigations/${task.task_id}/workbench?${query}`;
  };
  const title = String(task.opportunities?.opportunity_name ?? "公告核对");
  const identityTask = { ...task, binding_entities: task.binding_entities?.filter(entity => entity.kind === "announcement" || entity.id === entityId) };
  return <main id="main-content" className="page-shell human-test-shell investigation-shell">
    <nav className="breadcrumbs" aria-label="面包屑"><Link href={`/review/investigations?${new URLSearchParams(queue)}`}>返回调查队列</Link><Link href={`/review/investigations/${task.task_id}`}>完整材料与历史记录</Link></nav>
    <header className="human-test-hero"><div><p className="eyebrow">当前对象 · 当前步骤</p><h1>{title}</h1><p>先确认材料，再确认单位和岗位，最后逐字段、逐规则核对。</p></div></header>
    <aside className="fixture-notice">材料批准只允许继续内部核对。未确认、冲突和未接入条件保持未知；当前字段完成不等于完整资格或发布批准。</aside>
    <section className="human-test-panel" aria-labelledby="workbench-context-title">
      <h2 id="workbench-context-title">选择核对对象</h2>
      <p>公告：{title} · 单位：{unit?.name ?? "尚未选择 / 公告共同条件"} · 当前对象：{selected?.name ?? "尚未选择"}</p>
      <nav aria-label="公告与岗位对象">
        {task.binding_entities?.filter(entity => entity.kind === "announcement").map(entity => <p key={entity.id}><Link href={href(step, entity.id)} aria-current={entityId === entity.id ? "page" : undefined}>公告共同条件：{entity.name}</Link></p>)}
        {units.map(value => <details key={value.id} open={unit?.id === value.id || units.length === 1}><summary>{value.name}</summary>
          {task.binding_entities?.some(entity => entity.id === value.id) ? <p><Link href={href(step, value.id)}>单位共同条件：{value.name}</Link></p> : null}
          <ul>{value.positions.map(position => <li key={position.id}><Link href={href(step, position.id)} aria-current={entityId === position.id ? "page" : undefined}>{position.name}{position.code ? `（${position.code}）` : ""}</Link></li>)}</ul>
        </details>)}
      </nav>
      {!selected ? <p>请选择原件中实际存在的公告、单位或岗位；系统不会自动替你选择。</p> : <p>对象标识：{selected.id}。请核对岗位表名称、代码与实际行，不以名称相似推定归属。</p>}
    </section>
    <p className="field-help">字段与规则的未提交草稿仅保留在当前窗口内存，可切换对象后返回。刷新、关闭或重新登录不承诺恢复；离开前请保留必要的核对笔记。</p>
    <nav className="workbench-step-tabs" aria-label="当前审核步骤">{[["materials", "材料"], ["identity", "身份"], ["facts", "字段"], ["rules", "规则"]].map(([value, label]) => <Link key={value} href={href(value, entityId)} aria-current={step === value ? "step" : undefined}>{label}</Link>)}</nav>
    {step === "materials" ? <section className="human-test-panel"><h2>已保存的材料决定</h2>
      {task.review ? <><p>{task.review.decision === "APPROVE" ? "已批准内部材料，可继续确认单位和岗位。" : "材料已退回，请查看原记录。"}</p><blockquote>{task.review.reason}</blockquote><p>{formatDateTime(task.review.created_at)} · 审核员 {task.review.reviewer_id}</p></> : <p>尚无材料决定，请在完整材料页核对后由本人提交。</p>}
      <ul>{task.materials.map(material => <li key={material.artifact_id}><a href={`/review/investigations/${task.task_id}/materials/${encodeURIComponent(material.artifact_id)}`}>打开原件：{material.artifact_id}</a></li>)}</ul>
      <Link href={`/review/investigations/${task.task_id}#investigation-review-title`}>查看材料审核与文档准备</Link>
    </section> : null}
    {step === "identity" ? selected ? <><InvestigationEvidence task={task} /><InvestigationBindings task={identityTask} targets={targets} /></> : <p>先选择实际岗位，再核对其所属单位和公告；身份登记仍由本人明确选择。</p> : null}
    {(step === "facts" || step === "rules") && selected ? <>
      <p>当前对象：{selected.name} · {total ? `第 ${Math.min(offset + 1, total)} / ${total} 个字段或条件` : "尚无此对象的候选清单"}。公告共同条件和单位条件仍需分别核对。</p>
      {step === "facts" && slice ? <p>待处理或未决 {slice.attention_total ?? "待核对"} 项 · 未知或待裁决 {slice.unknown_total ?? "待核对"} 项。
        {slice.next_attention_offset != null ? <Link href={href(step, entityId, slice.next_attention_offset)}>查找下一未决字段</Link> : null}{" "}
        {slice.next_unknown_offset != null ? <Link href={href(step, entityId, slice.next_unknown_offset)}>查找未知或待裁决字段</Link> : null}
      </p> : null}
      {step === "facts" ? <InvestigationFactReview task={task} requestKey={randomUUID()} /> : <InvestigationRuleReview task={task} requestKey={randomUUID()} />}
      <nav aria-label="当前对象字段分页">{offset > 0 ? <Link href={href(step, entityId, offset - 1)}>上一个字段</Link> : null}{offset + 1 < total ? <Link className="button button-secondary" href={href(step, entityId, offset + 1)}>下一个字段</Link> : <span>此对象已到最后一页；请核对未决项与共同条件。</span>}</nav>
    </> : (step === "facts" || step === "rules") ? <p>请选择核对对象，字段和规则不会跨岗位混合展示。</p> : null}
  </main>;
}
