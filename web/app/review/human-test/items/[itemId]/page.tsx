import Link from "next/link";

import FactReviewPanel from "../../../../../components/human-test/fact-review-panel";
import PublicationPreviewPanel from "../../../../../components/human-test/publication-preview";
import RuleReviewPanel from "../../../../../components/human-test/rule-review-panel";
import { BootstrapButton } from "../../../../../components/human-test/stage-actions";
import { getLocalItem } from "../../../../../lib/local-human-test";

export default async function HumanTestItemPage({ params }: { params: Promise<{ itemId: string }> }) {
  const { itemId } = await params;
  const detail = await getLocalItem(itemId);
  return (
    <main id="main-content" className="page-shell human-test-shell">
      <nav className="breadcrumbs" aria-label="面包屑">
        <Link href="/review/human-test">人工测试控制台</Link><span>/</span>
        <Link href={`/review/human-test/runs/${detail.item.run_id}`}>运行详情</Link><span>/</span><span>条目</span>
      </nav>
      <header className="detail-heading">
        <p className="category-label">证据链条目</p>
        <h1>{detail.item.status}</h1>
        <p><code>{detail.item.item_id}</code></p>
      </header>
      {detail.item.status === "BOOTSTRAP_REVIEW" ? (
        <section className="human-test-panel human-test-high-impact">
          <h2>确定性引导需要处理</h2>
          <p>这里只能重新执行来源、标题、URL 和 Recipe 边界检查，不能人工绕过不合格来源。</p>
          <BootstrapButton itemId={detail.item.item_id} />
        </section>
      ) : null}
      <section className="human-test-panel" aria-labelledby="model-audit-title">
        <h2 id="model-audit-title">P9-B ModelCall / Ledger 摘要</h2>
        {!detail.model_audit ? <p>当前阶段尚无模型调用。</p> : (
          <>
            <dl className="audit-grid">
              <div><dt>ModelCall</dt><dd><code>{detail.model_audit.model_call_id}</code></dd></div>
              <div><dt>Egress</dt><dd>{detail.model_audit.egress_decision}</dd></div>
              <div><dt>终态</dt><dd>{detail.model_audit.final_status ?? "未终结"}</dd></div>
              <div><dt>Disposition</dt><dd>{detail.model_audit.terminal_disposition ?? "未终结"}</dd></div>
              <div><dt>Request hash</dt><dd><code>{detail.model_audit.canonical_request_hash}</code></dd></div>
              <div><dt>Payload hash</dt><dd><code>{detail.model_audit.actual_payload_hash ?? "未授权"}</code></dd></div>
            </dl>
            <div className="attempt-table" role="table" aria-label="Provider attempts">
              {detail.model_audit.attempts.map((attempt) => (
                <div className="attempt-row" role="row" key={attempt.attempt_number}>
                  <span>Attempt {attempt.attempt_number}</span><span>{attempt.outcome}</span>
                  <span>tokens {attempt.input_tokens ?? 0}/{attempt.output_tokens ?? 0}</span>
                  <span>{attempt.latency_ms ?? 0} ms</span><span>{attempt.cost_status ?? "未报告"}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </section>
      <FactReviewPanel itemId={detail.item.item_id} candidates={detail.candidates} />
      <RuleReviewPanel itemId={detail.item.item_id} candidates={detail.rules} />
      <PublicationPreviewPanel itemId={detail.item.item_id} preview={detail.publication_preview} />
    </main>
  );
}
