import GroupRuleReview from "../../../../../../components/investigations/group-rule-review";
import { loadGroupRuleReviewAction } from "../../../group-rule-review-actions";
export const dynamic = "force-dynamic";
export default async function Page({ params }: { params: Promise<{ taskId: string; prepId: string }> }) {
  const { taskId, prepId } = await params;
  const result = await loadGroupRuleReviewAction(taskId, prepId);
  return <GroupRuleReview key={JSON.stringify([taskId, prepId, result])} taskId={taskId} factId={result.ok ? result.value.fact_preparation_id : ""} savedId={prepId} initial={{ kind: "review", result }} />;
}
