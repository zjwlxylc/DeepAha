"use client";

import { useActionState } from "react";

import {
  appendAdjudicationAction,
  appendAssessmentAction,
  createApprovedLabelAction,
  type ReviewActionState,
} from "../app/review-actions";
import type { ReviewCaseDetail } from "../lib/review-feedback";

const initialState: ReviewActionState = { error: null, message: null };

function ActionMessage({ state }: { state: ReviewActionState }) {
  if (state.error) return <p className="form-alert" role="alert">{state.error}</p>;
  if (state.message) return <p className="form-success" role="status">{state.message}</p>;
  return null;
}

function EvidenceChecks({ detail }: { detail: ReviewCaseDetail }) {
  return (
    <div className="checkbox-list">
      {detail.evidence.map((item) => (
        <label className="check-label" key={item.evidence_ref_id}>
          <input type="checkbox" name="evidence_ref_id" value={item.evidence_ref_id} />
          {item.relation === "SUPPORTS" ? "支持" : "冲突"} · {item.evidence_ref_id}
        </label>
      ))}
    </div>
  );
}

export default function ReviewCasePanel({ detail }: { detail: ReviewCaseDetail }) {
  const [assessmentState, assessmentAction, assessmentPending] = useActionState(
    appendAssessmentAction,
    initialState,
  );
  const [adjudicationState, adjudicationAction, adjudicationPending] = useActionState(
    appendAdjudicationAction,
    initialState,
  );
  const [labelState, labelAction, labelPending] = useActionState(
    createApprovedLabelAction,
    initialState,
  );
  return (
    <article className="review-case">
      <header className="detail-heading">
        <p className="category-label">受控反馈审核</p>
        <h1>{detail.case.opportunity_title}</h1>
        <p>当前状态：{detail.case.status} · 优先级 {detail.case.priority}</p>
      </header>
      <section className="review-section" aria-labelledby="review-context-title">
        <h2 id="review-context-title">原始上下文</h2>
        <dl className="compact-facts">
          <div><dt>MatchSnapshot</dt><dd><code>{detail.match_snapshot_id}</code></dd></div>
          <div><dt>OpportunityVersion</dt><dd>v{detail.case.opportunity_version}</dd></div>
          <div><dt>结构化原因</dt><dd>{detail.structured_reason_code}</dd></div>
        </dl>
        <p>{detail.user_statement ?? "用户未提供补充说明。"}</p>
      </section>
      <section className="review-section" aria-labelledby="review-evidence-title">
        <h2 id="review-evidence-title">现有官方证据与补充</h2>
        <ul className="review-list">
          {detail.evidence.map((item) => (
            <li key={item.evidence_ref_id}>
              <code>{item.evidence_ref_id}</code> · {item.relation} · {item.locator_kind}
              {item.locator_value ? ` · ${item.locator_value}` : ""}
              {item.note ? <p>{item.note}</p> : null}
            </li>
          ))}
        </ul>
      </section>
      <section className="review-section" aria-labelledby="review-history-title">
        <h2 id="review-history-title">队列历史</h2>
        <ol className="review-list">
          {detail.history.map((item) => (
            <li key={item.version}>v{item.version} · {item.status} · {item.transition_reason}</li>
          ))}
        </ol>
      </section>
      <section className="review-section" aria-labelledby="assessment-title">
        <h2 id="assessment-title">追加评估</h2>
        <form className="review-form" action={assessmentAction}>
          <input type="hidden" name="review_case_id" value={detail.case.review_case_id} />
          <label className="check-label">
            <input type="checkbox" name="evidence_complete" />
            证据完整
          </label>
          <label>
            置信区间
            <select name="confidence_band" defaultValue="LOW">
              <option value="LOW">低</option>
              <option value="MEDIUM">中</option>
              <option value="HIGH">高</option>
            </select>
          </label>
          <label>
            影响风险
            <select name="risk_level" defaultValue="NORMAL">
              <option value="NORMAL">一般</option>
              <option value="HIGH_IMPACT">高影响</option>
            </select>
          </label>
          <label className="check-label">
            <input type="checkbox" name="conflict" />
            存在证据冲突
          </label>
          <EvidenceChecks detail={detail} />
          <label>
            评估理由
            <textarea name="rationale" maxLength={500} rows={4} required />
          </label>
          <ActionMessage state={assessmentState} />
          <button className="button button-secondary" type="submit" disabled={assessmentPending}>
            {assessmentPending ? "正在追加" : "追加评估"}
          </button>
        </form>
      </section>
      <section className="review-section" aria-labelledby="adjudication-title">
        <h2 id="adjudication-title">人工裁决</h2>
        {detail.latest_assessment ? (
          <form className="review-form" action={adjudicationAction}>
            <input type="hidden" name="review_case_id" value={detail.case.review_case_id} />
            <input
              type="hidden"
              name="confidence_assessment_id"
              value={detail.latest_assessment.confidence_assessment_id}
            />
            <label>
              裁决
              <select name="decision" defaultValue="NEEDS_EVIDENCE">
                <option value="NEEDS_EVIDENCE">需要补充证据</option>
                <option value="CONFLICT">存在冲突</option>
                <option value="CONFIRMED">确认</option>
                <option value="REJECTED">不采纳</option>
              </select>
            </label>
            <EvidenceChecks detail={detail} />
            <label>
              裁决理由
              <textarea name="reason" maxLength={500} rows={4} required />
            </label>
            <ActionMessage state={adjudicationState} />
            <button className="button button-primary" type="submit" disabled={adjudicationPending}>
              {adjudicationPending ? "正在裁决" : "追加裁决"}
            </button>
          </form>
        ) : <p>完成评估后才能裁决。</p>}
      </section>
      <section className="review-section" aria-labelledby="label-title">
        <h2 id="label-title">离线标签资产</h2>
        {detail.approved_label_id ? (
          <p>已创建标签：<code>{detail.approved_label_id}</code></p>
        ) : detail.case.status === "CONFIRMED" && detail.latest_adjudication ? (
          <form className="review-form" action={labelAction}>
            <input type="hidden" name="review_case_id" value={detail.case.review_case_id} />
            <input
              type="hidden"
              name="feedback_adjudication_id"
              value={detail.latest_adjudication.feedback_adjudication_id}
            />
            <EvidenceChecks detail={detail} />
            <label>
              批准目标或解释
              <textarea name="approved_target_value" maxLength={500} rows={4} required />
            </label>
            <ActionMessage state={labelState} />
            <button className="button button-primary" type="submit" disabled={labelPending}>
              {labelPending ? "正在创建" : "创建离线标签"}
            </button>
          </form>
        ) : <p>只有最新人工裁决为 CONFIRMED 时才能创建标签。</p>}
      </section>
    </article>
  );
}
