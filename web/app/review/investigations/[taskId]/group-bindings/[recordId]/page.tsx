import type { Metadata } from "next";
import GroupSourceReview from "../../../../../../components/investigations/group-source-review";
import { loadGroupRecordAction } from "../../../group-source-actions";
export const metadata: Metadata = { title: "已登记单位组来源" };
export const dynamic = "force-dynamic";
export default async function GroupSourceRecordPage({ params }: { params: Promise<{ taskId: string; recordId: string }> }) {
  const { taskId, recordId } = await params;
  const result = await loadGroupRecordAction(taskId, recordId);
  return <GroupSourceReview key={`${taskId}:${recordId}:${result.ok ? result.value.preview.source_hash : result.kind}`} taskId={taskId} recordId={recordId} initialResult={result} />;
}
