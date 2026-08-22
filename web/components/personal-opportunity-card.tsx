import Link from "next/link";

import type { PersonalPriorityItem } from "../lib/personal-opportunities";
import { formatDate } from "../lib/public-opportunities";
import { opportunityTypeLabel } from "./opportunity-card";

const eligibilityLabels = {
  ELIGIBLE: "资格条件已满足",
  LIKELY_ELIGIBLE: "大概率符合，仍需复核",
  UNCERTAIN: "信息不足，仍需确认",
  INELIGIBLE: "当前不符合",
} as const;

const reasonLabels: Record<string, string> = {
  PREFERRED_REGION: "符合优先地区",
  PREFERRED_TYPE: "符合优先类型",
  EARLIER_DEADLINE: "截止时间较近",
  STABLE_ID_TIE_BREAK: "稳定 ID 确定顺序",
};

export default function PersonalOpportunityCard({ item }: { item: PersonalPriorityItem }) {
  const { opportunity, ranking } = item;
  return (
    <article className="personal-opportunity-card">
      <div className="priority-row">
        <span className="priority-number">优先 {ranking.ordinal}</span>
        <span className={`eligibility-badge eligibility-${ranking.eligibility_status.toLowerCase()}`}>
          {eligibilityLabels[ranking.eligibility_status]}
        </span>
      </div>
      <p className="category-label">{opportunityTypeLabel(opportunity.type)}</p>
      <h2>
        <Link href={`/me/opportunities/${opportunity.public_id}`}>{opportunity.title}</Link>
      </h2>
      <p>{opportunity.issuer_name}</p>
      <dl className="compact-facts">
        <div>
          <dt>截止时间</dt>
          <dd>{formatDate(opportunity.deadline)}</dd>
        </div>
        <div>
          <dt>为什么排在这里</dt>
          <dd>
            {ranking.reason_codes
              .filter((reason) => reasonLabels[reason])
              .map((reason) => reasonLabels[reason])
              .join(" · ") || "按资格四态、截止时间和稳定 ID 排序"}
          </dd>
        </div>
      </dl>
      <Link className="button button-primary" href={`/me/opportunities/${opportunity.public_id}`}>
        查看判断与下一步
      </Link>
    </article>
  );
}
