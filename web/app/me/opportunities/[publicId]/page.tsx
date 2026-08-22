import Link from "next/link";

import ActionPanel from "../../../../components/action-panel";
import EligibilityExplanation from "../../../../components/eligibility-explanation";
import { opportunityChangeLabel } from "../../../../components/opportunity-card";
import { getPersonalOpportunity } from "../../../../lib/personal-opportunities";
import { formatDate } from "../../../../lib/public-opportunities";

export default async function PersonalOpportunityPage({ params }: { params: Promise<{ publicId: string }> }) {
  const { publicId } = await params;
  const detail = await getPersonalOpportunity(publicId);
  const opportunity = detail.opportunity;
  return (
    <main id="main-content" className="page-shell personal-shell">
      <nav className="breadcrumbs" aria-label="面包屑">
        <Link href="/me/opportunities">个人行动台</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">个人机会解释</span>
      </nav>
      <aside className="fixture-notice" aria-label="数据证据边界">
        本页是固定合成工程夹具，不代表真实个人资格、行动或发布资格。
      </aside>
      <header className="detail-heading">
        <p className="category-label">个人机会解释</p>
        <h1>{opportunity.title}</h1>
        <p>{opportunity.issuer_name} · 截止时间 {formatDate(opportunity.deadline)}</p>
        {opportunity.change_markers.length > 0 ? (
          <ul className="change-markers" aria-label="近期变化">
            {opportunity.change_markers.map((marker) => <li key={marker}>{opportunityChangeLabel(marker)}</li>)}
          </ul>
        ) : null}
      </header>
      <div className="personal-detail-grid">
        <EligibilityExplanation
          eligibility={detail.eligibility}
          evidence={opportunity.key_evidence}
        />
        <ActionPanel publicId={publicId} action={detail.action} />
      </div>
      <section className="official-summary" aria-labelledby="official-summary-title">
        <h2 id="official-summary-title">官方事实仍是最终入口</h2>
        <p>DeepAha 的解释不替代公告。行动前请复核附件、截止时间和最新变化。</p>
        <Link className="button button-secondary" href={`/opportunities/${publicId}`}>
          返回公开证据与变化历史
        </Link>
      </section>
    </main>
  );
}
