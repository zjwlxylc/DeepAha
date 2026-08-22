import type {
  MatchSnapshot,
  PublicEvidence,
} from "../lib/personal-opportunities";

const statusLabels = {
  ELIGIBLE: "符合条件",
  LIKELY_ELIGIBLE: "大概率符合",
  UNCERTAIN: "仍需确认",
  INELIGIBLE: "当前不符合",
} as const;

const fieldLabels: Record<string, string> = {
  education_level: "学历",
  major_code: "专业代码",
  graduation_year: "毕业年份",
  student_status: "学生状态",
  birth_date: "出生日期",
  hukou_region: "户籍地区",
  residence_region: "现居地",
  target_regions: "目标地区",
  certificates: "证书",
};

interface EligibilityExplanationProps {
  eligibility: MatchSnapshot;
  evidence: PublicEvidence[];
}

export default function EligibilityExplanation({ eligibility, evidence }: EligibilityExplanationProps) {
  const result = eligibility.eligibility_result;
  const evidenceIds = new Set(
    result.rule_evaluations.flatMap((evaluation) => evaluation.evidence_ref_ids),
  );
  const linkedEvidence = evidence.filter((item) => evidenceIds.has(item.evidence_ref_id));
  return (
    <section className={`eligibility-panel eligibility-${result.status.toLowerCase()}`} aria-labelledby="eligibility-title">
      <p className="section-kicker">资格判断 · 四态</p>
      <h2 id="eligibility-title">{statusLabels[result.status]}</h2>
      <p>
        判断固定绑定机会 v{eligibility.opportunity_version}、规则 v
        {eligibility.rule_set_version}、画像 v{eligibility.profile_version} 和场景日期
        {` ${eligibility.scenario_clock}`}。
      </p>
      <div className="explanation-grid">
        <section aria-labelledby="satisfied-title">
          <h3 id="satisfied-title">满足项</h3>
          <p>{result.satisfied_rule_ids.length > 0 ? `${result.satisfied_rule_ids.length} 条规则满足` : "暂无确定满足项"}</p>
        </section>
        <section aria-labelledby="conflict-title">
          <h3 id="conflict-title">冲突项</h3>
          <p>{result.conflict_rule_ids.length > 0 ? `${result.conflict_rule_ids.length} 条官方规则冲突` : "暂无确定冲突"}</p>
        </section>
        <section aria-labelledby="missing-title">
          <h3 id="missing-title">缺失项</h3>
          <p>
            {result.missing_fields.length > 0
              ? `缺少：${result.missing_fields.map((field) => fieldLabels[field] ?? field).join("、")}`
              : "没有影响当前判断的缺失字段"}
          </p>
        </section>
        <section aria-labelledby="risk-title">
          <h3 id="risk-title">风险与下一步</h3>
          <p>
            {result.review_reasons.length > 0
              ? "仍有不确定条件，请核对官方原文或补充画像。"
              : "仍应在行动前复核最新官方原文与附件。"}
          </p>
        </section>
      </div>
      {linkedEvidence.length > 0 ? (
        <ul className="evidence-links" aria-label="资格判断官方证据">
          {linkedEvidence.map((item) => (
            <li key={`${item.evidence_ref_id}:${item.field_path}`}>
              <a href={item.official_url} target="_blank" rel="noreferrer">
                查看官方证据
              </a>
              <span> · {item.field_path}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="risk-note">当前规则解释没有可公开回链的 EvidenceRef，请先不要作确定结论。</p>
      )}
    </section>
  );
}
