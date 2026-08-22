import Link from "next/link";

import type { FeedbackReviewStatus, FeedbackStatusDetail } from "../lib/feedback";
import { formatDateTime } from "../lib/public-opportunities";

const statusCopy: Record<FeedbackReviewStatus, { title: string; detail: string }> = {
  RECEIVED: {
    title: "已接收",
    detail: "纠错已作为原始反馈保存，等待受控审核。",
  },
  NEEDS_EVIDENCE: {
    title: "需要补充证据",
    detail: "现有证据还不足以确认，请回到官方证据页核对。",
  },
  CONFLICT: {
    title: "存在证据冲突",
    detail: "关联证据存在冲突，当前不会形成确定结论。",
  },
  CONFIRMED: {
    title: "已确认",
    detail: "纠错已被确认并可形成离线标签候选。",
  },
  REJECTED: {
    title: "未采纳",
    detail: "本次纠错未被采纳，原始反馈和处理历史仍会保留。",
  },
};

export function feedbackStatusLabel(status: FeedbackReviewStatus): string {
  return statusCopy[status].title;
}

export default function FeedbackStatus({ detail }: { detail: FeedbackStatusDetail }) {
  const copy = statusCopy[detail.feedback.status];
  return (
    <article className="feedback-status" aria-labelledby="feedback-status-title">
      <p className="section-kicker">纠错处理状态</p>
      <h2 id="feedback-status-title">{copy.title}</h2>
      <p>{copy.detail}</p>
      <p className="risk-note" role="note">
        用户纠错不会直接修改资格、历史匹配或排序；只有经审核的标签才能进入离线评估候选。
      </p>
      <dl className="compact-facts">
        <div>
          <dt>机会版本</dt>
          <dd>v{detail.feedback.opportunity_version}</dd>
        </div>
        <div>
          <dt>提交时间</dt>
          <dd>{formatDateTime(detail.feedback.created_at)}</dd>
        </div>
        <div>
          <dt>状态更新时间</dt>
          <dd>{formatDateTime(detail.feedback.status_updated_at)}</dd>
        </div>
      </dl>
      <h3>已关联 EvidenceRef</h3>
      {detail.evidence.length === 0 ? (
        <p>尚未关联官方证据。</p>
      ) : (
        <ul className="evidence-links">
          {detail.evidence.map((item) => (
            <li key={item.feedback_evidence_link_id}>
              <code>{item.evidence_ref_id}</code> · {item.relation === "SUPPORTS" ? "支持" : "冲突"}
            </li>
          ))}
        </ul>
      )}
      <div className="card-actions">
        <Link
          className="button button-secondary"
          href={`/me/opportunities/${detail.feedback.opportunity_public_id}`}
        >
          返回个人机会解释
        </Link>
      </div>
    </article>
  );
}
