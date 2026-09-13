import Link from "next/link";
import { redirect } from "next/navigation";
import WorkbenchShell from "../../../../../components/investigations/workbench-shell";
import { getInvestigationWorkbench, getInvestigationBindingTargets } from "../../../../../lib/investigations";
import { LocalHumanTestApiError } from "../../../../../lib/local-human-test";

export default async function WorkbenchPage({ params, searchParams }: {
  params: Promise<{ taskId: string }>; searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { taskId } = await params;
  const input = await searchParams ?? {};
  if (!input.entity_id && !input.step && input.view !== "advanced") {
    const q = new URLSearchParams();
    if (typeof input.queue === "string") q.set("queue", input.queue);
    redirect(`/review/investigations/${taskId}/check?${q}`);
  }
  const query = new URLSearchParams();
  for (const key of ["entity_id", "offset"]) if (typeof input[key] === "string") query.set(key, input[key]);
  const step = typeof input.step === "string" && ["materials", "identity", "facts", "rules"].includes(input.step) ? input.step : "identity";
  let task;
  let targets;
  try {
    task = await getInvestigationWorkbench(taskId, query);
    targets = step === "identity" && task.status === "APPROVED" && task.document_preparation?.status === "PREPARED" ? (await getInvestigationBindingTargets()).targets : [];

  } catch (error) {
    if (error instanceof LocalHumanTestApiError && [400, 401, 403, 404, 409].includes(error.status)) return <main id="main-content" className="page-shell"><h1>暂时无法打开该核对对象</h1><p role="alert">登录、对象归属或版本需要重新核对。未提交任何决定。</p><Link href={`/review/investigations/${taskId}`}>返回任务材料与记录</Link></main>;
    throw error;
  }
    return <WorkbenchShell task={task} step={step} targets={targets} queue={typeof input.queue === "string" ? input.queue : ""} />;
}
