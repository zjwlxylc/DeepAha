import type { InvestigationTask } from "./investigations";

/**
 * Client-safe helpers for the explicit "发起调查" control. This module must stay
 * free of `server-only` imports because `dispatch-button.tsx` is a client
 * component; `lib/investigations.ts` itself is `server-only` (it reads cookies
 * and calls the API), so these pure helpers live here instead. Both the list row
 * and the task detail page import them, guaranteeing a single set of
 * enabled/disabled semantics and copy.
 *
 * (Deviation from design §1.1, which placed these in `lib/investigations.ts`:
 * that module cannot be imported at runtime by a client component.)
 */

/** Prefix already includes `/api/v1/local-human-test` via `postInvestigation`. */
export function investigationDispatchPath(taskId: string): string {
  return `/investigation-runtime/tasks/${encodeURIComponent(taskId)}/dispatch`;
}

export interface InvestigationDispatchAvailability {
  /** Whether the "发起调查" control should be rendered at all. */
  visible: boolean;
  /** Whether the operator may submit a dispatch request right now. */
  enabled: boolean;
  /** Readable reason explaining why dispatch is unavailable (null when enabled). */
  reason: string | null;
}

/**
 * Single source of truth for the "发起调查" control. Dispatch is only offered
 * once the worker reports `dispatch_enabled` (worker RUNNING ∧ WMA
 * CONNECTION_VERIFIED ∧ sources > 0); a task that is not `QUEUED`, or already
 * requested, stays visible but disabled with an explicit reason. This function
 * never triggers dispatch on its own.
 */
export function investigationDispatchAvailability(
  task: Pick<InvestigationTask, "status" | "dispatch_requested_at" | "dispatch_pending"> & Partial<Pick<InvestigationTask, "runtime_id" | "remote_session_id">>,
  dispatchEnabled: boolean,
): InvestigationDispatchAvailability {
  if (!dispatchEnabled) return { visible: false, enabled: false, reason: null };
  if (["EXECUTION_UNCERTAIN", "COLLECTION_RETRYABLE", "EXPIRED"].includes(task.status)) {
    if (!task.runtime_id || !task.remote_session_id) return { visible: true, enabled: false, reason: "缺少可恢复的远端会话，无法回收材料；不会重新发起调查。" };
    return task.dispatch_pending
      ? { visible: true, enabled: false, reason: "材料回收请求已记录，请等待本次回收结果。" }
      : { visible: true, enabled: true, reason: null };
  }
  if (task.status !== "QUEUED") {
    return { visible: true, enabled: false, reason: "本任务不在可发起状态；无需重复发起。" };
  }
  if (task.dispatch_requested_at && task.dispatch_pending !== false) {
    return { visible: true, enabled: false, reason: "已发起，处理进程会在就绪后安排执行；无需重复发起。" };
  }
  return { visible: true, enabled: true, reason: null };
}

// Mirrors backend `list_dispatchable` RECOVERY_STATES (store.py): a background
// worker — not this page — drives recovery, and only ever downloads already
// produced material (never re-issues a prompt).
const recoveryStates = new Set(["INVESTIGATING", "EXECUTION_UNCERTAIN", "COLLECTING", "COLLECTION_RETRYABLE", "EXPIRED"]);

export interface InvestigationRecoveryAvailability {
  /** Whether the recovery entry applies to this task at all. */
  visible: boolean;
  /** Whether an existing remote session is available to download from. */
  recoverable: boolean;
  /** Honest explanation of what will (or cannot) happen. */
  reason: string;
}

/**
 * Describes the read-only "恢复材料" entry on the task detail page. There is no
 * user-facing recovery endpoint: the background worker scans these states and,
 * when a remote session is present and the lease has expired, downloads the
 * existing material. This helper only explains the situation — it never
 * dispatches and never re-issues a prompt.
 */
export function investigationRecoveryAvailability(
  task: Pick<InvestigationTask, "status" | "runtime_id" | "remote_session_id">,
): InvestigationRecoveryAvailability {
  if (!recoveryStates.has(task.status)) return { visible: false, recoverable: false, reason: "" };
  if (task.runtime_id && task.remote_session_id) {
    return {
      visible: true, recoverable: true,
      reason: "已有远端会话可用于回收材料：点击恢复材料后，处理进程仅下载已产出的内容，不会重新发出调查请求。",
    };
  }
  return {
    visible: true, recoverable: false,
    reason: "执行结果不确定，且缺少可恢复的远端会话标识，无法回收材料；不会盲目重新发起调查。",
  };
}
