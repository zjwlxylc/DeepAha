import GroupRuleReview from "../../../../../../../../components/investigations/group-rule-review";
import { loadGroupRulePreviewAction } from "../../../../../group-rule-actions";
export const dynamic = "force-dynamic";
export default async function Page({ params }: { params: Promise<{ taskId: string; prepId: string }> }) {
  const { taskId, prepId } = await params;
  const result = await loadGroupRulePreviewAction(taskId, prepId);
  return <GroupRuleReview key={JSON.stringify([taskId, prepId, result])} taskId={taskId} factId={prepId} initial={{ kind: "preview", result }} />;
}
