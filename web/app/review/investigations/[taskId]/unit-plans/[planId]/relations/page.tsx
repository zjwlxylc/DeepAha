import Link from "next/link";
import { loadRelation, loadRelationIndex } from "../../../../relation-actions";
import { relationPath } from "../../../../../../../lib/relation-review";
import RelationReview from "../../../../../../../components/investigations/relation-review";
export const dynamic = "force-dynamic";
export default async function Page({ params, searchParams }: { params: Promise<{ taskId: string; planId: string }>; searchParams: Promise<{ proposal?: string }> }) {
  const { taskId, planId } = await params, { proposal } = await searchParams;
  if (proposal) {
    const initial = await loadRelation(taskId, planId, proposal);
    return <RelationReview key={`${taskId}:${planId}:${proposal}:${JSON.stringify(initial)}`} task={taskId} plan={planId} id={proposal} initial={initial} />;
  }
  const result = await loadRelationIndex(taskId, planId);
  return <main id="main-content" className="page-shell human-test-shell investigation-shell">
    <nav className="breadcrumbs"><Link href={`/review/investigations/${encodeURIComponent(taskId)}/unit-plans/${encodeURIComponent(planId)}/cross-level`} prefetch={false}>返回跨层级条件总览</Link></nav>
    <h1>已保存的关系提案</h1><p>本列表仅用于查找提案，当前审核状态请进入详情核对。</p>
    {!result.ok ? <p role="alert">{result.error}</p> : result.value.proposals.length ? <ol className="human-test-panel">{result.value.proposals.map((p, i) => <li key={p.proposal_id}>
      <Link prefetch={false} href={relationPath(taskId, planId, p.proposal_id)}>关系提案 {i + 1}</Link><p>创建于 {p.created_at}</p>
    </li>)}</ol> : <p>该岗位尚无已保存提案。</p>}
  </main>;
}
