"use client";

import { useActionState, useState } from "react";

import { reviewInvestigationAction, type InvestigationActionState } from "../../app/review/investigations/actions";

const initialState: InvestigationActionState = { error: null, message: null, taskId: null };

export default function InvestigationReviewForm({ taskId, deliveryHash, requestKey }: { taskId: string; deliveryHash: string; requestKey: string }) {
  const [state, action, pending] = useActionState(reviewInvestigationAction, initialState);
  const [formKey] = useState(requestKey);
  const [decision, setDecision] = useState("REJECT");
  const [reason, setReason] = useState("");
  return (
    <form className="review-form" action={action} onReset={(event) => event.preventDefault()}>
      <input type="hidden" name="request_key" value={formKey} />
      <input type="hidden" name="task_id" value={taskId} />
      <input type="hidden" name="delivery_hash" value={deliveryHash} />
      <label>审核决定<select name="decision" value={decision} onChange={(event) => setDecision(event.target.value)}><option value="REJECT">退回材料</option><option value="APPROVE">批准内部材料</option></select></label>
      <label>核对理由<textarea name="reason" rows={4} maxLength={2000} value={reason} onChange={(event) => setReason(event.target.value)} required placeholder="记录已核对的原件、实体范围与尚存疑点。" /></label>
      <p className="field-help">由本人核对后提交；只有获授权的真人审核账号可以完成审核。</p>
      {state.error ? <p className="form-alert" role="alert">{state.error}</p> : null}
      {state.message ? <p className="form-success" role="status">{state.message}</p> : null}
      <button className="button button-primary" type="submit" disabled={pending || Boolean(state.message)}>{pending ? "正在记录" : "记录内部材料审核"}</button>
    </form>
  );
}
