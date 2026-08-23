import type { Metadata } from "next";
import Link from "next/link";

import FeedbackForm from "../../../../../components/feedback-form";
import {
  getPersonalOpportunity,
  getPersonalPriorities,
  getPersonalProfile,
} from "../../../../../lib/personal-opportunities";

export const metadata: Metadata = { title: "纠正个人机会判断" };

export default async function FeedbackPage({
  params,
}: {
  params: Promise<{ publicId: string }>;
}) {
  const { publicId } = await params;
  const [detail, priorities, profile] = await Promise.all([
    getPersonalOpportunity(publicId),
    getPersonalPriorities(),
    getPersonalProfile(),
  ]);
  if (!("eligibility_result" in detail.eligibility)) {
    throw new Error("feedback context unavailable");
  }
  const matchSnapshotId = detail.eligibility.snapshot_id;
  const item = priorities.items.find(
    (candidate) =>
      candidate.opportunity.public_id === publicId &&
      candidate.ranking.match_snapshot_id === matchSnapshotId,
  );
  if (!item) throw new Error("feedback context unavailable");
  return (
    <main id="main-content" className="page-shell personal-shell">
      <nav className="breadcrumbs" aria-label="面包屑">
        <Link href={`/me/opportunities/${publicId}`}>个人机会解释</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">纠正这条判断</span>
      </nav>
      <header className="page-heading personal-heading">
        <p className="eyebrow">Feedback · 用户纠错</p>
        <h1>纠正这条判断</h1>
        <p>提交内容会绑定当前 MatchSnapshot、OpportunityVersion 和画像版本。</p>
      </header>
      <aside className="fixture-notice" aria-label="数据证据边界">
        当前工程验证使用固定合成反馈，不代表真人纠错率、信任或发布资格。
      </aside>
      <FeedbackForm
        publicId={publicId}
        opportunityTitle={detail.opportunity.title}
        rankingSnapshotId={priorities.ranking_snapshot_id}
        matchSnapshotId={item.ranking.match_snapshot_id}
        opportunityVersion={item.ranking.opportunity_version}
        userStateVersion={profile.version}
        evidence={detail.opportunity.key_evidence}
      />
    </main>
  );
}
