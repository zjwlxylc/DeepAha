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
    label: "排除理由",
    hint: "排除不是已核对：此材料会改用无文本证据块的解析器，其字段不得作为块级依据，仅保留原件整文件引用。理由需填写 8–2000 个字符。",
    placeholder: "写明为何不解析此材料，例如格式没有可用解析器。",
    submit: "排除此材料（无机器证据块）",
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
