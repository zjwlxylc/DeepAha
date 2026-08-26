import Link from "next/link";

import { CancelRunButton } from "../../../../../components/human-test/stage-actions";
import { getLocalRun } from "../../../../../lib/local-human-test";
import { formatDateTime } from "../../../../../lib/public-opportunities";

export default async function HumanTestRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const detail = await getLocalRun(runId);
  const active = ["CREATED", "RUNNING"].includes(detail.run.status);
  return (
    <main id="main-content" className="page-shell human-test-shell">
      <nav className="breadcrumbs" aria-label="面包屑">
        <Link href="/review/human-test">人工测试控制台</Link><span>/</span><span>运行详情</span>
      </nav>
      <header className="detail-heading">
        <p className="category-label">{detail.run.mode}</p>
        <h1>运行 {detail.run.status}</h1>
        <p><code>{detail.run.run_id}</code></p>
      </header>
      <section className="human-test-panel">
        <h2>冻结身份与预算</h2>
        <dl className="audit-grid">
          <div><dt>Provider</dt><dd>{detail.run.provider}</dd></div>
          <div><dt>模型</dt><dd>{detail.run.model_id}</dd></div>
          <div><dt>模型快照</dt><dd>{detail.run.model_snapshot}</dd></div>
          <div><dt>更新时间</dt><dd>{formatDateTime(detail.run.updated_at)}</dd></div>
          <div><dt>官方请求</dt><dd>{detail.run.official_request_count} / 9</dd></div>
          <div><dt>LLM 调用</dt><dd>{detail.run.llm_call_count} / 8</dd></div>
        </dl>
        {active ? <CancelRunButton runId={detail.run.run_id} /> : null}
      </section>
      <section className="human-test-panel">
        <h2>来源处理条目</h2>
        <ol className="human-test-run-list">
          {detail.items.map((item) => (
            <li key={item.item_id}>
              <div><strong>{item.status}</strong>{item.error_code ? <span className="overdue-badge">{item.error_code}</span> : null}</div>
              <Link href={`/review/human-test/items/${item.item_id}`}>查看证据与人工决定</Link>
              <small><code>{item.recipe_id}</code></small>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
