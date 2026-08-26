"use client";

import { useActionState } from "react";

import {
  decideFactAction,
  type HumanTestActionState,
} from "../../app/review/human-test/actions";
import type { FactCandidate } from "../../lib/local-human-test";

const initialState: HumanTestActionState = { error: null, message: null };

function CandidateCard({ itemId, candidate }: { itemId: string; candidate: FactCandidate }) {
  const [state, action, pending] = useActionState(decideFactAction, initialState);
  return (
    <article className="candidate-card">
      <div className="candidate-grid">
        <section>
          <p className="section-kicker">LLM candidate</p>
          <h3>{candidate.field_name}</h3>
          <dl className="compact-facts">
            <div><dt>原始值</dt><dd><code>{JSON.stringify(candidate.raw_value)}</code></dd></div>
            <div><dt>规范值</dt><dd><code>{JSON.stringify(candidate.normalized_value_candidate)}</code></dd></div>
            <div><dt>置信度</dt><dd>{candidate.confidence ?? "未报告"}</dd></div>
            <div><dt>状态</dt><dd>{candidate.abstained ? "ABSTAINED" : candidate.candidate_reason_code}</dd></div>
          </dl>
        </section>
        <section>
          <p className="section-kicker">Official evidence</p>
          {candidate.evidence.length ? candidate.evidence.map((evidence) => (
            <blockquote className="official-evidence-block" key={evidence.block_id}>
              <p>{evidence.canonical_text_or_value}</p>
              <footer>
                {evidence.source_tier} · {evidence.block_type} · <a href={evidence.source_url}>官方原文</a>
              </footer>
            </blockquote>
          )) : <p className="form-alert">没有可授权展示的官方证据块，不能批准。</p>}
        </section>
      </div>
      {candidate.decision ? (
        <p className="form-success" role="status">已决定：{candidate.decision}</p>
      ) : (
        <form className="review-form" action={action}>
          <input type="hidden" name="item_id" value={itemId} />
          <input type="hidden" name="candidate_id" value={candidate.candidate_id} />
          <label>
            人工决定
            <select name="decision" defaultValue={candidate.abstained ? "UNKNOWN" : "REJECT"}>
              {!candidate.abstained ? <option value="APPROVE">批准为已验证事实</option> : null}
              <option value="REJECT">拒绝</option>
              {candidate.abstained ? <option value="UNKNOWN">保持未知</option> : null}
            </select>
          </label>
          <label>
            审核理由
            <textarea name="reason" rows={3} maxLength={500} required />
          </label>
          {state.error ? <p className="form-alert" role="alert">{state.error}</p> : null}
          {state.message ? <p className="form-success" role="status">{state.message}</p> : null}
          <button className="button button-primary" type="submit" disabled={pending || !candidate.evidence.length}>
            {pending ? "正在记录" : "记录事实决定"}
          </button>
        </form>
      )}
    </article>
  );
}

export default function FactReviewPanel({ itemId, candidates }: { itemId: string; candidates: FactCandidate[] }) {
  return (
    <section className="human-test-panel" aria-labelledby="fact-review-title">
      <h2 id="fact-review-title">事实审核：候选与官方证据并排</h2>
      <p className="risk-note" role="note">LLM 只提出候选。只有当前真人 reviewer 明确批准的字段才能进入 VerifiedFactSet。</p>
      <div className="candidate-list">
        {candidates.length ? candidates.map((candidate) => (
          <CandidateCard itemId={itemId} candidate={candidate} key={candidate.candidate_id} />
        )) : <p>当前没有事实候选。</p>}
      </div>
    </section>
  );
}
