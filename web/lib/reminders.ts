import "server-only";

import { personalFetch } from "./personal-opportunities";

export interface ReminderPreferenceSnapshot {
  preference_snapshot_id: string;
  preference_id: string;
  user_id: string;
  version: number;
  predecessor_snapshot_id: string | null;
  reminder_kind: "DEADLINE_CHANGED";
  enabled: boolean;
  cadence: "AS_SOON_AS_GOVERNED";
  target: "TEST_INBOX";
  actor_user_id: string;
  preference_policy_version: "phase8-deadline-reminder-v1";
  contract_version: "0.7.0";
  created_at: string;
}

export interface ReminderInboxEntry {
  inbox_entry_id: string;
  reminder_id: string;
  user_id: string;
  opportunity_id: string;
  opportunity_public_id: string;
  opportunity_title: string;
  event_id: string;
  from_version: number;
  to_version: number;
  old_closes_on: string;
  new_closes_on: string;
  direction: "ADVANCED" | "EXTENDED";
  previous_evidence_ref_id: string;
  current_evidence_ref_id: string;
  previous_official_url: string;
  current_official_url: string;
  personal_detail_path: string;
  detected_at: string;
  delivered_at: string;
  target: "TEST_INBOX";
  contract_version: "0.7.0";
}

export interface ReminderInboxPage {
  items: ReminderInboxEntry[];
  count: number;
}

export function getDeadlineReminderPreference(): Promise<ReminderPreferenceSnapshot | null> {
  return personalFetch<ReminderPreferenceSnapshot | null>(
    "/api/v1/me/reminder-preferences/deadline-change",
  );
}

export function getReminderInbox(): Promise<ReminderInboxPage> {
  return personalFetch<ReminderInboxPage>("/api/v1/me/reminder-inbox");
}

export function setDeadlineReminderPreference(
  enabled: boolean,
  idempotencyKey: string,
): Promise<ReminderPreferenceSnapshot> {
  return personalFetch<ReminderPreferenceSnapshot>(
    "/api/v1/me/reminder-preferences/deadline-change",
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({ enabled }),
    },
  );
}
