import type { Metadata } from "next";
import Link from "next/link";

import FeedbackStatus from "../../../../components/feedback-status";
import { getFeedback } from "../../../../lib/feedback";

export const metadata: Metadata = { title: "纠错处理详情" };

export default async function FeedbackDetailPage({
  params,
}: {
  params: Promise<{ feedbackId: string }>;
}) {
  const { feedbackId } = await params;
  const detail = await getFeedback(feedbackId);
  return (
    <main id="main-content" className="page-shell personal-shell">
      <nav className="breadcrumbs" aria-label="面包屑">
        <Link href="/me/feedback">我的纠错状态</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">处理详情</span>
      </nav>
      <FeedbackStatus detail={detail} />
    </main>
  );
}
