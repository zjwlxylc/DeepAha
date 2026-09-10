import GroupInheritance from "../../../../../../../components/investigations/group-inheritance";
import { loadGroupInheritanceAction } from "../../../../group-inheritance-actions";
export const dynamic = "force-dynamic";
export default async function Page({ params }: { params: Promise<{ taskId: string; planId: string }> }) {
  const { taskId, planId } = await params;
  const result = await loadGroupInheritanceAction(taskId, planId);
  return <GroupInheritance key={`${taskId}:${planId}:${JSON.stringify(result)}`} taskId={taskId} planId={planId} initialResult={result} />;
}
