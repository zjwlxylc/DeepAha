import CrossLevel from "../../../../../../../components/investigations/cross-level";
import { loadCrossLevelAction } from "../../../../cross-level-actions";
export const dynamic = "force-dynamic";
export default async function Page({ params }: { params: Promise<{ taskId: string; planId: string }> }) {
  const { taskId, planId } = await params;
  const result = await loadCrossLevelAction(taskId, planId);
  return <CrossLevel key={`${taskId}:${planId}:${JSON.stringify(result)}`} taskId={taskId} planId={planId} initialResult={result} />;
}
