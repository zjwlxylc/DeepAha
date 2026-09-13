"use client";

import Link from "next/link";
import type { InvestigationQueueItem, InvestigationSource } from "../../lib/investigations";
import { formatDateTime } from "../../lib/public-opportunities";
import { investigationStatus } from "./status";
import DispatchButton from "./dispatch-button";


export default function ReviewQueue({ tasks, dispatchEnabled, requestKeys, filters, nextCursor, sources }: {
  sources: InvestigationSource[]; filters: string; nextCursor: string | null; tasks: InvestigationQueueItem[]; dispatchEnabled: boolean; requestKeys: Record<string, string>;
}) {
  const params = new URLSearchParams(filters);
  const next = new URLSearchParams(filters);
  if (nextCursor) next.set("cursor", nextCursor);
  const detailUrl = (task: InvestigationQueueItem) => `/review/investigations/${encodeURIComponent(task.task_id)}${task.status === "APPROVED" ? "/check" : ""}?queue=${encodeURIComponent(filters)}`;
  const pending = tasks.filter(task => task.status === "PENDING_REVIEW").length;
  const failures = tasks.filter(task => task.error_code).length;
  return <section className="human-test-panel" aria-labelledby="investigation-list-title">
    <div className="human-test-panel-heading"><div><p className="eyebrow">审核工作台</p><h2 id="investigation-list-title">调查任务</h2></div><a className="button button-secondary" href="#new-investigation">添加公告</a></div>
    <div className="review-queue-summary"><div><strong>{pending}</strong><span>本页待审核</span></div><div><strong>{failures}</strong><span>本页需处理</span></div><div><strong>{tasks.length}</strong><span>本页调查记录</span></div></div>
    <p>先打开一份公告，对照原文核对内容，再记录你的决定。运行中的任务可查看进度。</p>
    <form action="/review/investigations" method="get" className="review-queue-filters">
      <label>搜索公告<input name="q" defaultValue={params.get("q") ?? ""} maxLength={200} /></label>
      <label>任务状态<select name="status" defaultValue={params.get("status") ?? ""}><option value="">全部状态</option>{["QUEUED", "CREATING", "PREPARING", "INVESTIGATING", "COLLECTING", "PENDING_REVIEW", "APPROVED", "REJECTED", "FAILED_PREPARATION", "EXECUTION_UNCERTAIN", "COLLECTION_RETRYABLE", "FAILED_VALIDATION", "EXPIRED"].map(status => <option key={status} value={status}>{investigationStatus(status)}</option>)}</select></label>
      <label>来源<select name="source" defaultValue={params.get("source") ?? ""}><option value="">全部来源</option>{sources.map(source => <option key={source.source_id} value={source.source_id}>{source.authority_name}</option>)}</select></label>
      <button className="button button-secondary" type="submit">筛选任务</button>
      <Link href="/review/investigations">重置筛选</Link>
    </form>
    {tasks.length ? <ol className="human-test-run-list review-queue-list">{tasks.map(task => <li key={task.task_id}>
        <div><span className="status-badge">{investigationStatus(task.status)}</span>{task.calibration ? <span>校准样本</span> : null}</div>
        <Link className="review-queue-title" href={detailUrl(task)}>{task.title}</Link>
        <small>更新于 {formatDateTime(task.updated_at)} · 已保存 {task.material_count} 份材料</small><p>下一步：{task.next_step}</p>
        <div><Link className="button button-primary" href={detailUrl(task)}>{task.status === "PENDING_REVIEW" ? "开始核对" : "打开任务"}</Link>
          <DispatchButton task={task} dispatchEnabled={dispatchEnabled} requestKey={requestKeys[task.task_id]} compact /></div>
        <details><summary>查看来源地址</summary><p className="investigation-hash">{task.notice_url}</p></details>
      </li>)}</ol> : <div className="empty-state"><h3>{filters ? "没有符合筛选的任务" : "还没有调查任务"}</h3><p>{filters ? "可调整筛选或返回首屏重新查询。" : "先在下方添加一份公告，再明确发起调查。"}</p></div>}
    <nav aria-label="调查队列分页"><Link href={`/review/investigations?${(() => { const first = new URLSearchParams(filters); first.delete("cursor"); return first.toString(); })()}`}>返回首屏</Link>{nextCursor ? <Link className="button button-secondary" href={`/review/investigations?${next}`}>下一页</Link> : <span>已到最后一页</span>}</nav>
  </section>;
}
