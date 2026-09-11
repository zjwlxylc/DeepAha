import ScopePreflight from "../../../../../../../components/investigations/scope-preflight";
import { loadScopePreflight } from "../../../../scope-actions";
export const dynamic = "force-dynamic";
export const metadata = { title: "条件范围预检" };
export default async function Page({ params }: { params: Promise<{ taskId: string; planId: string }> }) {
  const { taskId, planId } = await params;
  const initial = await loadScopePreflight(taskId, planId);
  return <ScopePreflight key={`${taskId}:${planId}:${JSON.stringify(initial)}`} task={taskId} plan={planId} initial={initial} />;
}
