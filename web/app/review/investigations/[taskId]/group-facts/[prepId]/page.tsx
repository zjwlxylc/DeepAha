import type { Metadata } from "next";
import GroupFactReview from "../../../../../../components/investigations/group-fact-review";
import { loadGroupFactRecordAction } from "../../../group-fact-actions";
export const metadata: Metadata = { title: "已保存单位组字段审核" };
export const dynamic = "force-dynamic";
export default async function GroupFactRecordPage({ params }: { params: Promise<{ taskId: string; prepId: string }> }) {
  const { taskId, prepId } = await params;
  const result = await loadGroupFactRecordAction(taskId, prepId);
  return <GroupFactReview key={`${taskId}:${prepId}:${result.ok ? JSON.stringify(result.value.record) : result.kind}`} taskId={taskId} prepId={prepId} initialResult={result} />;
}
