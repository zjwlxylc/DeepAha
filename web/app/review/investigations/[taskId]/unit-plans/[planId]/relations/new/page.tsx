import { loadProposalContext } from "../../../../../proposal-actions";
import ProposalForm from "../../../../../../../../components/investigations/relation-proposal";
export const dynamic = "force-dynamic";
export default async function Page({ params }: { params: Promise<{ taskId: string; planId: string }> }) {
  const { taskId, planId } = await params;
  return <ProposalForm key={`${taskId}:${planId}`} task={taskId} plan={planId} initial={await loadProposalContext(taskId, planId)} />;
}
