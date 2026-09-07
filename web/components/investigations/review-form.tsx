"use client";

import { useActionState } from "react";

import { reviewInvestigationAction, type InvestigationActionState } from "../../app/review/investigations/actions";

const initialState: InvestigationActionState = { error: null, message: null, taskId: null };

export default function InvestigationReviewForm({ taskId, deliveryHash }: { taskId: string; deliveryHash: string }) {
  const [state, action, pending] = useActionState(reviewInvestigationAction, initialState);
  return (
    <form className="review-form" action={action}>
      <input type="hidden" name="task_id" value={taskId} />
      <input type="hidden" name="delivery_hash" value={deliveryHash} />
      <label>审核决定<select name="decision" defaultValue="REJECT"><option value="REJECT">退回材料</option><option value="APPROVE">批准内部材料</option></select></label>
      <label>核对理由<textarea name="reason" rows={4} maxLength={2000} required placeholder="记录已核对的原件、实体范围与尚存疑点。" /></label>
      <p className="field-help">由本人核对后提交；只有获授权的真人审核账号可以完成审核。</p>
      {state.error ? <p className="form-alert" role="alert">{state.error}</p> : null}
      {state.message ? <p className="form-success" role="status">{state.message}</p> : null}
      <button className="button button-primary" type="submit" disabled={pending || Boolean(state.message)}>{pending ? "正在记录" : "记录内部材料审核"}</button>
    </form>
  );
}
