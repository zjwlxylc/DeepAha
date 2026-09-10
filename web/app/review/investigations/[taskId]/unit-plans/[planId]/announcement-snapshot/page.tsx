import type { Metadata } from "next";
import AnnouncementSnapshotReview from "../../../../../../../components/investigations/announcement-snapshot-review";
import { loadAnnouncementPreviewAction } from "../../../../announcement-snapshot-actions";

export const metadata: Metadata = { title: "公告继承范围预览" };
export const dynamic = "force-dynamic";

export default async function AnnouncementSnapshotPreviewPage({ params }: { params: Promise<{ taskId: string; planId: string }> }) {
  const { taskId, planId } = await params;
  const result = await loadAnnouncementPreviewAction({ task_id: taskId, base_plan_id: planId });
  return <AnnouncementSnapshotReview key={`${taskId}:${planId}:${result.ok ? result.value.input.dependencies_hash : result.kind}`} taskId={taskId} basePlanId={planId} initialResult={result} />;
}
