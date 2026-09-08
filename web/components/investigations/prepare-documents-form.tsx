"use client";

import { useActionState, useState } from "react";
import { prepareInvestigationDocumentsAction, type InvestigationActionState } from "../../app/review/investigations/actions";

const initialState: InvestigationActionState = { error: null, message: null, taskId: null };

export default function PrepareDocumentsForm({ taskId, deliveryHash, requestKey }: { taskId: string; deliveryHash: string; requestKey: string }) {
  const [state, action, pending] = useActionState(prepareInvestigationDocumentsAction, initialState);
  const [formKey] = useState(requestKey);
  return <form className="review-form" action={action} onReset={(event) => event.preventDefault()}>
    <input type="hidden" name="request_key" value={formKey} />
    <input type="hidden" name="task_id" value={taskId} />
    <input type="hidden" name="delivery_hash" value={deliveryHash} />
    <button className="button button-secondary" type="submit" disabled={pending}>{pending ? "正在准备文档…" : "准备文档证据"}</button>
    {state.error ? <p role="alert" className="form-error">{state.error}</p> : null}
    {state.message ? <p role="status">{state.message}</p> : null}
  </form>;
}
