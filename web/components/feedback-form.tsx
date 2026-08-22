"use client";

import { useActionState } from "react";

import {
  submitFeedbackAction,
  type FeedbackActionState,
} from "../app/feedback-actions";
import type { PublicEvidence } from "../lib/public-opportunities";

const initialState: FeedbackActionState = { error: null };

export default function FeedbackForm({
  publicId,
  opportunityTitle,
  rankingSnapshotId,
  matchSnapshotId,
  opportunityVersion,
  userStateVersion,
  evidence,
}: {
  publicId: string;
  opportunityTitle: string;
  rankingSnapshotId: string;
  matchSnapshotId: string;
  opportunityVersion: number;
  userStateVersion: number;
  evidence: PublicEvidence[];
}) {
  const [state, action, pending] = useActionState(submitFeedbackAction, initialState);
  return (
    <form className="feedback-form" action={action}>
      <input type="hidden" name="public_id" value={publicId} />
      <input type="hidden" name="ranking_snapshot_id" value={rankingSnapshotId} />
      <input type="hidden" name="match_snapshot_id" value={matchSnapshotId} />
      <input type="hidden" name="opportunity_version" value={opportunityVersion} />
      <input type="hidden" name="user_state_version" value={userStateVersion} />
      <fieldset>
        <legend>纠错内容</legend>
        <p>机会：{opportunityTitle}</p>
        <label>
          需要纠正什么
          <select name="claim_kind" defaultValue="EXPLANATION_UNCLEAR" required>
            <option value="ELIGIBILITY_CORRECTION">资格判断有误</option>
            <option value="OPPORTUNITY_FACT_CORRECTION">机会事实有误或过期</option>
            <option value="EXPLANATION_UNCLEAR">解释不清楚</option>
            <option value="RANKING_IRRELEVANT">当前排序不相关</option>
          </select>
        </label>
        <label>
          补充说明（可跳过）
          <textarea name="user_statement" maxLength={500} rows={5} />
        </label>
        <p className="privacy-note" role="note">
          不要填写身份证号、手机号、邮箱或其他敏感个人信息。说明最多 500 个字符。
        </p>
      </fieldset>
      <fieldset>
        <legend>关联已经展示的官方证据</legend>
        {evidence.length === 0 ? (
          <p>当前没有可关联的官方 EvidenceRef；审核可能要求补充证据。</p>
        ) : (
          <div className="checkbox-list">
            {evidence.map((item) => (
              <label className="check-label" key={`${item.evidence_ref_id}:${item.field_path}`}>
                <input
                  type="checkbox"
                  name="evidence_ref_id"
                  value={item.evidence_ref_id}
                />
                官方证据 · {item.field_path} · {item.evidence_ref_id}
              </label>
            ))}
          </div>
        )}
      </fieldset>
      <fieldset>
        <legend>用途授权</legend>
        <label className="check-label">
          <input type="checkbox" name="consent" required />
          同意仅用于反馈审核与验证；纠错不会直接修改线上规则、历史匹配、资格或排序。
        </label>
      </fieldset>
      {state.error ? <p className="form-alert" role="alert">{state.error}</p> : null}
      <button className="button button-primary" type="submit" disabled={pending}>
        {pending ? "正在提交" : "提交纠错"}
      </button>
    </form>
  );
}
