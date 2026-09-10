import GroupApplicability from "../../../../../../../../../components/investigations/group-applicability";
import { loadGroupApplicabilityReview } from "../../../../../../group-applicability-decision-actions";
export const dynamic = "force-dynamic";
export default async function Page({ params }: { params: Promise<{ taskId: string; planId: string; sourcePreparationId: string; candidateId: string }> }) {
  const p = await params;
  const identity = { task_id: p.taskId, target_plan_id: p.planId, source_rule_preparation_id: p.sourcePreparationId, source_rule_candidate_id: p.candidateId };
  const initial = await loadGroupApplicabilityReview(identity);
  return <GroupApplicability key={JSON.stringify([identity, initial])} identity={identity} initial={initial} />;
}
