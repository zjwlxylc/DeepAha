import Link from "next/link";

import {
  formatDate,
  formatDateTime,
  type PublicOpportunityCard as PublicOpportunityCardData,
} from "../lib/public-opportunities";
import TrustFact from "./trust-fact";

const typeLabels: Record<string, string> = {
  PUBLIC_INSTITUTION_JOB: "事业单位招聘",
  STATE_OWNED_ENTERPRISE_JOB: "国央企校招",
  CIVIL_SERVICE: "公务员招录",
  GRASSROOTS_PROGRAM: "基层项目",
  YOUTH_POLICY_BENEFIT: "青年政策权益",
  COMPETITION: "竞赛",
  RESEARCH_PROGRAM: "科研计划",
  SCHOLARSHIP: "奖学金",
  YOUTH_DEVELOPMENT_PROGRAM: "青年成长计划",
};

const statusLabels: Record<string, string> = {
  DRAFT: "草稿",
  OPEN: "报名中",
  CLOSING_SOON: "即将截止",
  CLOSED: "已结束",
  CANCELLED: "已取消",
  SUPERSEDED: "已被更正替代",
  UNKNOWN: "状态待核对",
};

const changeLabels: Record<string, string> = {
  CORRECTED: "内容已更正",
  DEADLINE_CHANGED: "截止时间已变化",
  ATTACHMENT_REPLACED: "附件已替换",
  CANCELLED: "机会已取消",
  REOPENED: "机会已重新开放",
  UPDATED: "信息已更新",
};

export function opportunityTypeLabel(value: string): string {
  return typeLabels[value] ?? value;
}

export function opportunityStatusLabel(value: string): string {
  return statusLabels[value] ?? value;
}

export function opportunityChangeLabel(value: string): string {
  return changeLabels[value] ?? value;
}

interface OpportunityCardProps {
  opportunity: PublicOpportunityCardData;
}

export default function OpportunityCard({ opportunity }: OpportunityCardProps) {
  const headingId = `title-${opportunity.public_id}`;
  return (
    <article className="opportunity-card" aria-labelledby={headingId}>
      <div className="card-heading-row">
        <p className="category-label">{opportunityTypeLabel(opportunity.type)}</p>
        <span className={`status-badge status-${opportunity.status.toLowerCase()}`}>
          {opportunityStatusLabel(opportunity.status)}
        </span>
      </div>
      <h2 id={headingId}>
        <Link href={`/opportunities/${opportunity.public_id}`}>{opportunity.title}</Link>
      </h2>
      <p className="stable-id">{opportunity.public_id}</p>
      <p className="data-label">数据标签：{opportunity.data_label}</p>
      {opportunity.change_markers.length > 0 ? (
        <ul className="change-markers" aria-label="变化标记">
          {opportunity.change_markers.map((marker) => (
            <li key={marker}>{opportunityChangeLabel(marker)}</li>
          ))}
        </ul>
      ) : null}
      <dl className="card-facts">
        <TrustFact label="发布单位">{opportunity.issuer_name}</TrustFact>
        <TrustFact label="地域">
          {[opportunity.jurisdiction, ...opportunity.locations].join(" · ")}
        </TrustFact>
        <TrustFact label="发布时间">
          <time dateTime={opportunity.published_at}>{formatDateTime(opportunity.published_at)}</time>
        </TrustFact>
        <TrustFact label="截止时间">
          <time dateTime={opportunity.deadline}>{formatDate(opportunity.deadline)}</time>
        </TrustFact>
        <TrustFact label="DeepAha 最后核验">
          <time dateTime={opportunity.last_verified_at}>
            {formatDateTime(opportunity.last_verified_at)}
          </time>
        </TrustFact>
      </dl>
      <div className="card-actions">
        <Link className="button button-primary" href={`/opportunities/${opportunity.public_id}`}>
          查看证据与变化
        </Link>
        <Link
          className="button button-secondary"
          href={`/opportunities/${opportunity.public_id}/fit-check`}
        >
          判断我是否适合
        </Link>
      </div>
    </article>
  );
}
