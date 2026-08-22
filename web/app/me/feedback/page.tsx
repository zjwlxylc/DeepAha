import type { Metadata } from "next";
import Link from "next/link";

import { feedbackStatusLabel } from "../../../components/feedback-status";
import { listFeedback } from "../../../lib/feedback";
import { formatDateTime } from "../../../lib/public-opportunities";

export const metadata: Metadata = { title: "我的纠错状态" };

export default async function FeedbackListPage() {
  const page = await listFeedback();
  return (
    <main id="main-content" className="page-shell personal-shell">
      <header className="page-heading personal-heading">
        <p className="eyebrow">Feedback Status · 纠错状态</p>
        <h1>我的纠错状态</h1>
        <p>这里只显示公开处理状态，不显示审核员、内部置信度或风险标记。</p>
      </header>
      {page.items.length === 0 ? (
        <div className="empty-state" role="status">
          <h2>还没有提交纠错</h2>
          <Link className="button button-secondary" href="/me/opportunities">返回个人行动台</Link>
        </div>
      ) : (
        <ul className="feedback-list" aria-label="我的纠错记录">
          {page.items.map((item) => (
            <li key={item.feedback_event_id}>
              <Link href={`/me/feedback/${item.feedback_event_id}`}>
                {feedbackStatusLabel(item.status)} · 机会 v{item.opportunity_version}
              </Link>
              <span>{formatDateTime(item.status_updated_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
