import type { Metadata } from "next";
import GroupRulePreview from "../../../../../../../components/investigations/group-rule-preview";
import { loadGroupRulePreviewAction } from "../../../../group-rule-actions";
export const metadata: Metadata = { title: "单位组规则预览" };
export const dynamic = "force-dynamic";
export default async function GroupRulePage({ params }: { params: Promise<{ taskId: string; prepId: string }> }) {
  const { taskId, prepId } = await params;
  const result = await loadGroupRulePreviewAction(taskId, prepId);
  return <GroupRulePreview key={JSON.stringify([taskId, prepId, result])} taskId={taskId} prepId={prepId} initialResult={result} />;
}
