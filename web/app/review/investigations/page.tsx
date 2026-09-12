import type { Metadata } from "next";
import Link from "next/link";
import { randomUUID } from "node:crypto";

import InvestigationCreateForm from "../../../components/investigations/create-form";
import DispatchButton from "../../../components/investigations/dispatch-button";
import { investigationStatus } from "../../../components/investigations/status";
import { getInvestigations, getInvestigationSources } from "../../../lib/investigations";
import { formatDateTime } from "../../../lib/public-opportunities";
import RuntimePanel from "../../../components/investigations/runtime-panel";
import { humanTestFetch, LocalHumanTestApiError } from "../../../lib/local-human-test";
import { investigationLoginHelp, type InvestigationRuntime } from "../../../lib/investigation-runtime";

export const metadata: Metadata = { title: "官方机会调查" };

export default async function InvestigationsPage() {
  let loaded;
  try {
    loaded = await Promise.all([getInvestigations(), getInvestigationSources(), humanTestFetch<InvestigationRuntime>("/investigation-runtime")]);
  } catch (error) {
    if (error instanceof LocalHumanTestApiError && [401, 403].includes(error.status)) return <main id="main-content" className="page-shell"><h1>需要本地审核登录</h1><p role="alert">{investigationLoginHelp}</p></main>;
    throw error;
  }
  const [{ tasks }, { sources }, runtime] = loaded;
  return (
    <main id="main-content" className="page-shell human-test-shell investigation-shell">
      <nav className="breadcrumbs" aria-label="面包屑"><Link href="/review/human-test">内部工作台</Link><span aria-hidden="true">/</span><span aria-current="page">官方机会调查</span></nav>
      <header className="human-test-hero"><div><p className="eyebrow">官方证据 · 内部调查</p><h1>官方机会调查</h1><p>从已批准来源登记明确公告，查看回收原件，逐项核对后记录内部审核。</p></div></header>
      <aside className="fixture-notice" aria-label="调查证据边界">调查输出是候选材料。内部批准不等于正式机会、资格规则或公开目录发布；校准样本不计为隐藏盲测。</aside>
      <RuntimePanel initial={runtime} />
      <InvestigationCreateForm sources={sources} requestKey={randomUUID()} />
      <section className="human-test-panel" aria-labelledby="investigation-list-title">
        <div className="human-test-panel-heading"><h2 id="investigation-list-title">调查任务</h2><span className="status-badge">{tasks.length} 项</span></div>
        {tasks.length ? <ol className="human-test-run-list">{tasks.map((task) => <li key={task.task_id}>
          <div><span className="status-badge">{investigationStatus(task.status)}</span>{task.calibration ? <span>校准样本</span> : null}</div>
          <Link href={`/review/investigations/${encodeURIComponent(task.task_id)}`}>{typeof task.opportunities?.opportunity_name === "string" ? task.opportunities.opportunity_name : task.brief}</Link>
          <small>{task.notice_url}</small><small>更新于 {formatDateTime(task.updated_at)}</small>
          <DispatchButton task={task} dispatchEnabled={runtime.dispatch_enabled} requestKey={randomUUID()} compact />
        </li>)}</ol> : <div className="empty-state"><h3>还没有调查任务</h3><p>先选择来源并填写具体公告，登记后可查看状态。</p></div>}
      </section>
    </main>
  );
}
