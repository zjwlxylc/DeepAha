import type { Metadata } from "next";
import AnnouncementSnapshotReview from "../../../../../../components/investigations/announcement-snapshot-review";
import { loadAnnouncementRecordAction } from "../../../announcement-snapshot-actions";

export const metadata: Metadata = { title: "公告继承范围快照" };
export const dynamic = "force-dynamic";

export default async function AnnouncementSnapshotPage({ params }: { params: Promise<{ taskId: string; snapshotId: string }> }) {
  const { taskId, snapshotId } = await params;
  const result = await loadAnnouncementRecordAction(taskId, snapshotId);
  return <AnnouncementSnapshotReview key={`${taskId}:${snapshotId}:${result.ok ? result.value.input.dependencies_hash : result.kind}`} taskId={taskId} snapshotId={snapshotId} initialResult={result} />;
}
