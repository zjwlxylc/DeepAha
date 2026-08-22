import type { Metadata } from "next";
import Link from "next/link";

import ReviewCasePanel from "../../../../components/review-case-panel";
import { getReviewCase } from "../../../../lib/review-feedback";

export const metadata: Metadata = { title: "受控反馈案件" };

export default async function ReviewCasePage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  const detail = await getReviewCase(caseId);
  return (
    <main id="main-content" className="page-shell personal-shell review-shell">
      <nav className="breadcrumbs" aria-label="面包屑">
        <Link href="/review/feedback">反馈审核队列</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">案件</span>
      </nav>
      <ReviewCasePanel detail={detail} />
    </main>
  );
}
