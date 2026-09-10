import type { RelationView } from "./relation-review";
export interface RelationQueueView {
  task_id: string; target_plan_id: string; source_review_hash: string; read_at: string;
  executable: false; overall_qualification: "UNCERTAIN"; next_after: string | null;
  proposals: { proposal_id: string; created_at: string; relation: string; reason: string;
    condition_ids: string[]; status: RelationView["review"]["status"]; is_own_proposal: boolean }[];
}
