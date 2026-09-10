import { loadRelation } from "../../../../relation-actions";
import { loadRelationQueue } from "../../../../queue-actions";
import RelationQueue from "../../../../../../../components/investigations/relation-queue";
import RelationReview from "../../../../../../../components/investigations/relation-review";
export const dynamic = "force-dynamic";
export default async function Page({ params, searchParams }: { params: Promise<{ taskId: string; planId: string }>; searchParams: Promise<{ proposal?: string }> }) {
  const { taskId, planId } = await params, { proposal } = await searchParams;
  if (proposal) {
    const initial = await loadRelation(taskId, planId, proposal);
    return <RelationReview key={`${taskId}:${planId}:${proposal}:${JSON.stringify(initial)}`} task={taskId} plan={planId} id={proposal} initial={initial} />;
  }
  return <RelationQueue key={`${taskId}:${planId}`} task={taskId} plan={planId} initial={await loadRelationQueue(taskId, planId)} />;
}
