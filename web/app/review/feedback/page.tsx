import type { Metadata } from "next";
import Link from "next/link";

import { getReviewQueue } from "../../../lib/review-feedback";
import { formatDateTime } from "../../../lib/public-opportunities";

export const metadata: Metadata = { title: "反馈审核队列" };

export default async function ReviewQueuePage() {
  const queue = await getReviewQueue();
  return (
    <main id="main-content" className="page-shell personal-shell review-shell">
      <header className="page-heading personal-heading">
        <p className="eyebrow">Controlled Review · 受控审核</p>
        <h1>反馈审核队列</h1>
        <p>有限队列按优先级、到期时间和稳定 ID 排序；没有批量操作或用户搜索。</p>
      </header>
      <aside className="fixture-notice" aria-label="审核证据边界">
        当前 reviewer 凭证与个人会话严格分离；合成审核不得写成真人裁决指标。
      </aside>
      {queue.items.length === 0 ? (
        <div className="empty-state" role="status">
          <h2>当前没有待处理反馈</h2>
        </div>
      ) : (
        <ol className="review-queue" aria-label="待处理反馈">
          {queue.items.slice(0, 100).map((item) => (
            <li key={item.review_case_id}>
              <div>
                <span className="status-badge">优先级 {item.priority}</span>
                {item.overdue ? <span className="overdue-badge">已逾期</span> : null}
              </div>
              <Link href={`/review/feedback/${item.review_case_id}`}>
                {item.opportunity_title} · {item.claim_kind}
              </Link>
              <span>到期 {formatDateTime(item.due_at)}</span>
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}
