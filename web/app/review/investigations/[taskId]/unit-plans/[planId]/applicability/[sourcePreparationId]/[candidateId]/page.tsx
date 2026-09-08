import { randomUUID } from "node:crypto";
import type { Metadata } from "next";
import Link from "next/link";
import RuleApplicabilityReview from "../../../../../../../../../components/investigations/rule-applicability-review";
import { loadRuleApplicabilityAction } from "../../../../../../rule-applicability-actions";

export const metadata: Metadata = { title: "公告规则适用性审阅" };
export const dynamic = "force-dynamic";

export default async function RuleApplicabilityPage({ params }: { params: Promise<{ taskId: string; planId: string; sourcePreparationId: string; candidateId: string }> }) {
  const { taskId, planId, sourcePreparationId, candidateId } = await params;
  const identity = { task_id: taskId, target_plan_id: planId, source_rule_preparation_id: sourcePreparationId, source_rule_candidate_id: candidateId };
  const result = await loadRuleApplicabilityAction(identity);
  const back = `/review/investigations/${encodeURIComponent(taskId)}/unit-plans/${encodeURIComponent(planId)}`;
  return result.ok
    ? <RuleApplicabilityReview key={`${taskId}:${planId}:${sourcePreparationId}:${candidateId}:${result.value.context_hash}:${result.value.latest?.decision_id ?? ""}`} identity={identity} initialView={result.value} requestKey={randomUUID()} />
    : <main id="main-content" className="page-shell human-test-shell investigation-shell">
      <Link href={back} prefetch={false}>返回条件快照</Link>
      <section className="human-test-panel" role="alert"><h1>适用性审阅暂不可用</h1><p>{result.error}</p></section>
      <a className="button button-secondary" href={`${back}/applicability/${encodeURIComponent(sourcePreparationId)}/${encodeURIComponent(candidateId)}`}>重新读取最新状态</a>
    </main>;
}
