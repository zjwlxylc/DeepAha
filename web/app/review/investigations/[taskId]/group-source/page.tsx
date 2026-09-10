import type { Metadata } from "next";
import GroupSourceReview from "../../../../../components/investigations/group-source-review";
import { loadGroupPreviewAction } from "../../group-source-actions";
export const metadata: Metadata = { title: "单位组来源预览" };
export const dynamic = "force-dynamic";
export default async function GroupSourcePage({ params, searchParams }: { params: Promise<{ taskId: string }>; searchParams: Promise<{ entity_id?: string | string[] }> }) {
  const { taskId } = await params, query = await searchParams;
  const entityId = typeof query.entity_id === "string" ? query.entity_id : "";
  const result = await loadGroupPreviewAction({ task_id: taskId, entity_id: entityId });
  return <GroupSourceReview key={`${taskId}:${entityId}:${result.ok ? result.value.preview.source_hash : result.kind}`} taskId={taskId} entityId={entityId} initialResult={result} />;
}
