"use client";

import Link from "next/link";
import type { InvestigationTask } from "../../lib/investigations";
import { formatDateTime } from "../../lib/public-opportunities";
import { investigationStatus } from "./status";
import DispatchButton from "./dispatch-button";
import ReviewBrowser from "./review-browser";

export default function ReviewQueue({ tasks, dispatchEnabled, requestKeys }: {
  tasks: InvestigationTask[]; dispatchEnabled: boolean; requestKeys: Record<string, string>;
}) {
  const title = (task: InvestigationTask) => typeof task.opportunities?.opportunity_name === "string" ? task.opportunities.opportunity_name : task.brief;
  const pending = tasks.filter(task => task.status === "PENDING_REVIEW").length;
  const failures = tasks.filter(task => task.error_code).length;
  return <section className="human-test-panel" aria-labelledby="investigation-list-title">
    <div className="human-test-panel-heading"><div><p className="eyebrow">审核工作台</p><h2 id="investigation-list-title">调查任务</h2></div><a className="button button-secondary" href="#new-investigation">添加公告</a></div>
    <div className="review-queue-summary"><div><strong>{pending}</strong><span>等待你审核</span></div><div><strong>{failures}</strong><span>调查需要处理</span></div><div><strong>{tasks.length}</strong><span>本页调查记录</span></div></div>
    <p>先打开一份公告，对照原文核对内容，再记录你的决定。运行中的任务可查看进度。</p>
    {tasks.length ? <ReviewBrowser items={tasks} label="调查任务" searchText={task => `${title(task)} ${task.notice_url} ${investigationStatus(task.status)}`}
      needsAttention={task => task.status === "PENDING_REVIEW" || !!task.error_code}>
      {visible => <ol className="human-test-run-list review-queue-list">{visible.map(task => <li key={task.task_id}>
        <div><span className="status-badge">{investigationStatus(task.status)}</span>{task.calibration ? <span>校准样本</span> : null}</div>
        <Link className="review-queue-title" href={`/review/investigations/${encodeURIComponent(task.task_id)}`}>{title(task)}</Link>
        <small>更新于 {formatDateTime(task.updated_at)} · 已保存 {task.materials.length} 份材料</small>
        <div><Link className="button button-primary" href={`/review/investigations/${encodeURIComponent(task.task_id)}`}>{task.status === "PENDING_REVIEW" ? "开始核对" : "打开任务"}</Link>
          <DispatchButton task={task} dispatchEnabled={dispatchEnabled} requestKey={requestKeys[task.task_id]} compact /></div>
        <details><summary>查看来源地址</summary><p className="investigation-hash">{task.notice_url}</p></details>
      </li>)}</ol>}
    </ReviewBrowser> : <div className="empty-state"><h3>还没有调查任务</h3><p>先在下方添加一份公告，再明确发起调查。</p></div>}
  </section>;
}
