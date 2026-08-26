"use client";

import { useActionState } from "react";

import { decideRuleAction, type HumanTestActionState } from "../../app/review/human-test/actions";
import type { RuleCandidate } from "../../lib/local-human-test";

const initialState: HumanTestActionState = { error: null, message: null };

function RuleCard({ itemId, candidate }: { itemId: string; candidate: RuleCandidate }) {
  const [state, action, pending] = useActionState(decideRuleAction, initialState);
  return (
    <article className="rule-card">
      <h3>高影响资格规则候选</h3>
      <pre>{JSON.stringify(candidate.proposed_rule_payload, null, 2)}</pre>
      {candidate.decision ? <p>已决定：{candidate.decision}</p> : (
        <form className="review-form" action={action}>
          <input type="hidden" name="item_id" value={itemId} />
          <input type="hidden" name="rule_candidate_id" value={candidate.rule_candidate_id} />
          <label>
            人工决定
            <select name="decision" defaultValue="NEEDS_ADJUDICATION">
              <option value="APPROVE">批准规则</option>
              <option value="REJECT">拒绝规则</option>
              <option value="NEEDS_ADJUDICATION">需要进一步裁决</option>
            </select>
          </label>
          <label>决定理由<textarea name="reason" rows={3} maxLength={500} required /></label>
          {state.error ? <p className="form-alert" role="alert">{state.error}</p> : null}
          {state.message ? <p className="form-success" role="status">{state.message}</p> : null}
          <button className="button button-primary" type="submit" disabled={pending}>
            {pending ? "正在记录" : "记录规则决定"}
          </button>
        </form>
      )}
    </article>
  );
}

export default function RuleReviewPanel({ itemId, candidates }: { itemId: string; candidates: RuleCandidate[] }) {
  return (
    <section className="human-test-panel human-test-high-impact" aria-labelledby="rule-review-title">
      <h2 id="rule-review-title">规则审核</h2>
      <p>没有人工批准规则时，个人资格结论上限固定为 <strong>UNCERTAIN</strong>。</p>
      <div className="candidate-list">
        {candidates.length ? candidates.map((candidate) => (
          <RuleCard itemId={itemId} candidate={candidate} key={candidate.rule_candidate_id} />
        )) : <p>当前没有可批准的规则候选；系统不会从事实静默推断硬资格。</p>}
      </div>
    </section>
  );
}
