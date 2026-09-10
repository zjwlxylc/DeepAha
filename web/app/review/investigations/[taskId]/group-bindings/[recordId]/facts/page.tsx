import type { Metadata } from "next";
import GroupFactReview from "../../../../../../../components/investigations/group-fact-review";
import { loadGroupFactStartAction } from "../../../../group-fact-actions";
export const metadata: Metadata = { title: "准备单位组字段审核" };
export const dynamic = "force-dynamic";
export default async function GroupFactStartPage({ params }: { params: Promise<{ taskId: string; recordId: string }> }) {
  const { taskId, recordId } = await params;
  const result = await loadGroupFactStartAction(taskId, recordId);
  return <GroupFactReview key={`${taskId}:${recordId}:${result.ok ? result.value.source.preview.source_hash : result.kind}`} taskId={taskId} groupId={recordId} initialResult={result} />;
}
