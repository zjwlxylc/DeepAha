import type { Metadata } from "next";
import Link from "next/link";
import UnitPlanView from "../../../../../../components/investigations/unit-plan-view";
import { getInvestigation, type InvestigationTask } from "../../../../../../lib/investigations";
import { humanTestFetch, LocalHumanTestApiError } from "../../../../../../lib/local-human-test";
import type { InvestigationUnitSnapshot } from "../../../../../../lib/unit-snapshots";

export const metadata: Metadata = { title: "内部条件快照" };
export const dynamic = "force-dynamic";

export default async function UnitPlanPage({ params }: { params: Promise<{ taskId: string; planId: string }> }) {
  const { taskId, planId } = await params;
  const back = `/review/investigations/${encodeURIComponent(taskId)}`;
  let data: [InvestigationUnitSnapshot, InvestigationTask] | null = null;
  let failure: string | null = null;
  try {
    data = await Promise.all([
      humanTestFetch<InvestigationUnitSnapshot>(`/investigations/${encodeURIComponent(taskId)}/unit-plans/${encodeURIComponent(planId)}`),
      getInvestigation(taskId),
    ]);
  } catch (error) {
    if (!(error instanceof LocalHumanTestApiError)) throw error;
    failure = [401, 403].includes(error.status)
      ? "当前会话没有查看权限，请使用已授权的审核会话。"
      : error.status === 404 ? "未找到此任务的条件快照。"
        : "证据或关联版本可能已变化，请返回任务核对后重新整理。";
  }
  return <main id="main-content" className="page-shell human-test-shell investigation-shell"><nav className="breadcrumbs" aria-label="面包屑"><Link href={back}>返回调查任务</Link><span aria-hidden="true">/</span><span aria-current="page">条件快照</span></nav>
    {data ? <UnitPlanView snapshot={data[0]} task={data[1]} /> : <section className="human-test-panel" role="alert"><h1>快照暂不可用</h1><p>{failure}</p></section>}
  </main>;
}
