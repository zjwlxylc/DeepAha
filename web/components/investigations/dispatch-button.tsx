"use client";

import { useActionState, useState } from "react";

import { requestInvestigationDispatchAction, type InvestigationActionState } from "../../app/review/investigations/actions";
import { investigationDispatchAvailability } from "../../lib/investigation-dispatch";
import type { InvestigationTask } from "../../lib/investigations";

const initialState: InvestigationActionState = { error: null, message: null, taskId: null };

/**
 * Explicit operator control to dispatch a queued investigation. It is a client
 * component because it drives a {@link requestInvestigationDispatchAction}
 * server action through `useActionState`. Availability and the disabled reason
 * come from the shared {@link investigationDispatchAvailability} pure function,
 * so the row and the task detail page never diverge. The control is hidden
 * entirely while the system is not ready, disabled with a reason otherwise, and
 * only ever dispatches when the operator clicks it (never on mount).
 */
export default function DispatchButton({ task, dispatchEnabled, requestKey, compact = false }: {
  task: Pick<InvestigationTask, "task_id" | "status" | "dispatch_requested_at" | "dispatch_pending"> & Partial<Pick<InvestigationTask, "runtime_id" | "remote_session_id">>;
  dispatchEnabled: boolean;
  requestKey: string;
  compact?: boolean;
}) {
  const [formKey] = useState(requestKey);
  const [state, action, pending] = useActionState(requestInvestigationDispatchAction, initialState);
  const availability = investigationDispatchAvailability(task, dispatchEnabled);
  if (!availability.visible) return null;
  const recovering = ["EXECUTION_UNCERTAIN", "COLLECTION_RETRYABLE", "EXPIRED"].includes(task.status);
  const label = recovering ? "恢复材料" : "发起调查";
  const reasonId = `dispatch-reason-${task.task_id}`;
  return <form className="card-actions investigation-dispatch" action={action} onReset={(event) => event.preventDefault()}>
    <input type="hidden" name="kind" value={recovering ? "recover" : "new"} />
    <input type="hidden" name="task_id" value={task.task_id} />
    <input type="hidden" name="request_key" value={formKey} />
    <button className={compact ? "button button-secondary" : "button button-primary"} type="submit"
      disabled={pending || !availability.enabled}
      title={availability.reason ?? undefined}
      aria-describedby={availability.reason ? reasonId : undefined}>
      {pending ? `正在${label}…` : availability.enabled ? label : `${label}（暂不可用）`}
    </button>
    {availability.reason ? <p id={reasonId} className="field-help">{availability.reason}</p> : null}
    {state.error ? <p role="alert" className="form-error">{state.error}</p> : null}
    {state.message ? <p role="status">{state.message}</p> : null}
  </form>;
}
