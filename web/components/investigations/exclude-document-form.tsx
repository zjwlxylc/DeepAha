"use client";

import { useActionState, useState } from "react";
import { excludeInvestigationDocumentAction, revokeInvestigationDocumentAction, type InvestigationActionState } from "../../app/review/investigations/actions";

const initialState: InvestigationActionState = { error: null, message: null, taskId: null };

// Exclusion hands the material to the opaque parser: a document is produced, but
// no block carries quotable text, so the material can never back a block-level
// field decision. Both modes restate that boundary instead of implying review.
const modes = {
  exclude: {
    action: excludeInvestigationDocumentAction,
    label: "为什么暂不解析",
    hint: "文件会完整保留并可下载，但其中的文字不能作为系统确认条件的依据。这不表示附件已经审核通过，也不会消除其中可能存在的要求。请填写 8–2000 字的实际原因。",
    placeholder: "例如：系统暂不支持该格式，需要人工阅读原件。",
    submit: "仅保留原件，暂不解析",
    pending: "正在记录排除…",
  },
  revoke: {
    action: revokeInvestigationDocumentAction,
    label: "撤销排除理由",
    hint: "撤销后此材料恢复为待解析状态，需要重新准备文档证据；撤销同样不等于已核对。依据需填写 8–2000 个字符。",
    placeholder: "写明撤销排除并恢复解析的依据。",
    submit: "撤销排除",
    pending: "正在撤销排除…",
  },
} as const;

export default function ExcludeDocumentForm({ mode = "exclude", taskId, deliveryHash, materialId, requestKey }: {
  mode?: keyof typeof modes; taskId: string; deliveryHash: string; materialId: string; requestKey: string;
}) {
  const config = modes[mode];
  const [state, action, pending] = useActionState(config.action, initialState);
  const [formKey] = useState(requestKey);
  return <form className="review-form" action={action} onReset={(event) => event.preventDefault()}>
    <input type="hidden" name="request_key" value={formKey} />
    <input type="hidden" name="task_id" value={taskId} />
    <input type="hidden" name="delivery_hash" value={deliveryHash} />
    <input type="hidden" name="material_id" value={materialId} />
    <label>{config.label}<textarea name="reason" rows={3} minLength={8} maxLength={2000} required placeholder={config.placeholder} /></label>
    <p className="field-help">{config.hint}</p>
    {state.error ? <p className="form-alert" role="alert">{state.error}</p> : null}
    {state.message ? <p className="form-success" role="status">{state.message}</p> : null}
    <button className="button button-secondary" type="submit" disabled={pending}>{pending ? config.pending : config.submit}</button>
  </form>;
}
