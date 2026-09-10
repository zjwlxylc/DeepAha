import type { Metadata } from "next";
import Link from "next/link";
import UnitPlanView from "../../../../../../components/investigations/unit-plan-view";
import { getInvestigation, type InvestigationTask } from "../../../../../../lib/investigations";
import { humanTestFetch, LocalHumanTestApiError } from "../../../../../../lib/local-human-test";
import type { InvestigationUnitSnapshot } from "../../../../../../lib/unit-snapshots";
import { loadGroupApplicabilityEntries } from "../../../group-applicability-actions";
import { groupApplicabilityPath } from "../../../../../../lib/group-applicability";
import { groupInheritancePath } from "../../../../../../lib/group-inheritance";
import { crossLevelPath } from "../../../../../../lib/cross-level";

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
  const groups = data ? await loadGroupApplicabilityEntries(taskId, planId) : null;
  if (groups && !groups.ok) { data = null; failure = groups.error; }
  return <main id="main-content" className="page-shell human-test-shell investigation-shell"><nav className="breadcrumbs" aria-label="面包屑"><Link href={back}>返回调查任务</Link><span aria-hidden="true">/</span><span aria-current="page">条件快照</span></nav>
    {data ? <><UnitPlanView snapshot={data[0]} task={data[1]} /><section className="human-test-panel"><h2>组规则与本岗位</h2>
      <p>逐条核对组规则的岗位适用范围；完整资格仍待确认。</p>
      <p><Link prefetch={false} href={crossLevelPath(taskId, planId)}>查看公告、组与岗位全部条件</Link></p>
      <Link prefetch={false} href={groupInheritancePath(taskId, planId)}>查看全部组条件的范围预览</Link>
      {groups?.ok ? (groups.value.length ? <ul>{groups.value.map(c => <li key={`${c.source_rule_preparation_id}:${c.source_rule_candidate_id}`}><Link prefetch={false} href={groupApplicabilityPath(c)}>{c.source_group.label} · 查看组规则依据</Link></li>)}</ul> : <p>当前没有可查看的已批准组规则记录。这不代表没有组条件。</p>) : <p role="alert">{groups && !groups.ok ? groups.error : "组规则入口暂不可用。"}</p>}
    </section></> : <section className="human-test-panel" role="alert"><h1>快照暂不可用</h1><p>{failure}</p></section>}
  </main>;
}
