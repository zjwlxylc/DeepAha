import type { Metadata } from "next";
import Link from "next/link";
import { randomUUID } from "node:crypto";

import InvestigationEvidence, { safeOfficialUrl } from "../../../../components/investigations/evidence";
import InvestigationReviewForm from "../../../../components/investigations/review-form";
import InvestigationDocuments from "../../../../components/investigations/documents";
import InvestigationFactReview from "../../../../components/investigations/fact-review";
import InvestigationRuleReview from "../../../../components/investigations/rule-review";
import InvestigationBindings from "../../../../components/investigations/bindings";
import GroupSourceLinks from "../../../../components/investigations/group-source-links";
import DispatchButton from "../../../../components/investigations/dispatch-button";
import NextSteps from "../../../../components/investigations/next-steps";
import { investigationFailureMessage, investigationStatus } from "../../../../components/investigations/status";
import { getInvestigation, getInvestigationBindingTargets } from "../../../../lib/investigations";
import { investigationRecoveryAvailability } from "../../../../lib/investigation-dispatch";
import type { InvestigationRuntime } from "../../../../lib/investigation-runtime";
import { humanTestFetch } from "../../../../lib/local-human-test";
import { formatDateTime } from "../../../../lib/public-opportunities";

export const metadata: Metadata = { title: "调查材料与内部审核" };

export default async function InvestigationPage({ params }: { params: Promise<{ taskId: string }> }) {
  const { taskId } = await params;
  const task = await getInvestigation(taskId);
  const title = task.opportunities?.opportunity_name;
  const targets = task.status === "APPROVED" && task.document_preparation?.status === "PREPARED"
    ? (await getInvestigationBindingTargets()).targets : [];
  // The dispatch control is only meaningful once the worker/WMA readiness flag is
  // true. Readiness is fetched defensively: a missing session or an unready
  // subsystem degrades to "no dispatch control" and never triggers a check.
  let dispatchEnabled = false;
  try {
    dispatchEnabled = (await humanTestFetch<InvestigationRuntime>("/investigation-runtime")).dispatch_enabled;
  } catch {
    dispatchEnabled = false;
  }
  const recovery = investigationRecoveryAvailability(task);
  return (
    <main id="main-content" data-investigation-status={task.status} className="page-shell human-test-shell investigation-shell">
      <nav className="breadcrumbs" aria-label="面包屑"><Link href="/review/investigations">官方机会调查</Link><span aria-hidden="true">/</span><span aria-current="page">材料与审核</span></nav>
      <header className="human-test-hero"><div><p className="eyebrow">调查材料 · 内部核对</p><h1>{typeof title === "string" && title ? title : "调查任务详情"}</h1><p>{task.brief}</p><span className="status-badge">{investigationStatus(task.status)}</span>{task.calibration ? <p>校准样本：不计为隐藏盲测。</p> : null}</div></header>
      <aside className="fixture-notice" aria-label="内部审核边界">内部审核不等于正式机会、资格规则或公开目录发布。字段依据仍需本人核对，未披露或冲突的信息保持未知。</aside>
      <p>{safeOfficialUrl(task.notice_url) ? <a href={safeOfficialUrl(task.notice_url)} target="_blank" rel="noopener noreferrer">查看原始官方公告</a> : "官方公告地址不可用"} · 更新于 {formatDateTime(task.updated_at)}</p>
      {task.status === "QUEUED" && !task.dispatch_pending ? <p className="risk-note">任务已登记，尚未发起。请使用下方“发起调查”入口明确发起；本页不会自动开始调查。</p> : null}
      <NextSteps task={task} />
      <section className="human-test-panel" id="investigation-dispatch" aria-labelledby="investigation-dispatch-title">
        <h2 id="investigation-dispatch-title">发起调查与处理进度</h2>
        <p>当前阶段：<strong>{investigationStatus(task.status)}</strong> · 更新于 {formatDateTime(task.updated_at)}</p>
        {task.error_code
          ? <p className="risk-note">本任务已记录安全失败原因（诊断编号 {task.error_code}），完整说明见下方「待处理问题」。</p>
          : <p className="field-help">尚未记录失败原因。</p>}
        <DispatchButton task={task} dispatchEnabled={dispatchEnabled} requestKey={randomUUID()} />
        {recovery.visible ? <div className="risk-note" data-testid="recovery-entry"><strong>恢复材料</strong><p>{recovery.reason}</p></div> : null}
        <p className="field-help">是否发起由你明确点击决定；页面加载或刷新不会自动发起，未就绪时不会显示发起按钮。</p>
      </section>
      {task.issues.length || task.error_code ? <section className="human-test-panel" aria-labelledby="investigation-issues-title"><h2 id="investigation-issues-title">待处理问题</h2>{task.error_code ? <><p>{investigationFailureMessage(task.error_code)}</p><p>系统不会自动重新调查。已有材料需完成回收与核验后，才能提交审核。</p></> : <p>这些问题需处理并重新核对，不能据此认定调查完整。</p>}<ul>{task.issues.map((issue, index) => <li key={index}>{issue}</li>)}</ul>{task.error_code ? <details><summary>故障标识（供排查）</summary><code>{task.error_code}</code></details> : null}</section> : null}
      <InvestigationEvidence task={task} />
      <InvestigationDocuments task={task} />
      <InvestigationBindings task={task} targets={targets} />
      <GroupSourceLinks task={task} />
      <InvestigationFactReview task={task} requestKey={randomUUID()} key={`${task.entity_binding?.binding_id}:${task.evidence_check?.check_id}`} />
      <InvestigationRuleReview task={task} requestKey={randomUUID()} key={`rules:${task.entity_binding?.binding_id}:${task.evidence_check?.check_id}`} />
      <section className="human-test-panel" aria-labelledby="investigation-review-title">
        <h2 id="investigation-review-title">内部材料审核</h2>
        {task.review ? <dl className="compact-facts"><div><dt>审核决定</dt><dd>{task.review.decision === "APPROVE" ? "批准内部材料" : "退回材料"}</dd></div><div><dt>核对理由</dt><dd>{task.review.reason}</dd></div><div><dt>记录时间</dt><dd>{formatDateTime(task.review.created_at)}</dd></div><div><dt>审核员标识</dt><dd>{task.review.reviewer_id}</dd></div></dl> : task.status === "PENDING_REVIEW" && task.delivery_hash ? <InvestigationReviewForm taskId={task.task_id} deliveryHash={task.delivery_hash} requestKey={randomUUID()} key={task.delivery_hash} /> : <p>当前材料尚不可审核。请先完成回收与核验；执行失败不会被当作已完成。</p>}
      </section>
      <details className="human-test-panel"><summary>任务版本与原始候选（补充核对）</summary><dl className="compact-facts"><div><dt>任务标识</dt><dd>{task.task_id}</dd></div><div><dt>调查约定版本</dt><dd className="investigation-hash">{task.contract_hash}</dd></div><div><dt>材料版本</dt><dd className="investigation-hash">{task.delivery_hash ?? "尚未交付"}</dd></div><div><dt>登记时间</dt><dd>{formatDateTime(task.created_at)}</dd></div></dl><pre className="investigation-json">{JSON.stringify(task.opportunities, null, 2)}</pre></details>
    </main>
  );
}
