"use client";

import { useActionState } from "react";

import {
  bootstrapItemAction,
  cancelHumanTestRunAction,
  type HumanTestActionState,
} from "../../app/review/human-test/actions";

const initialState: HumanTestActionState = { error: null, message: null };

function Message({ state }: { state: HumanTestActionState }) {
  if (state.error) return <p className="form-alert" role="alert">{state.error}</p>;
  if (state.message) return <p className="form-success" role="status">{state.message}</p>;
  return null;
}

export function CancelRunButton({ runId }: { runId: string }) {
  const [state, action, pending] = useActionState(cancelHumanTestRunAction, initialState);
  return (
    <form action={action}>
      <input type="hidden" name="run_id" value={runId} />
      <Message state={state} />
      <button className="button button-secondary" type="submit" disabled={pending}>
        {pending ? "正在请求停止" : "停止后续处理"}
      </button>
    </form>
  );
}

export function BootstrapButton({ itemId }: { itemId: string }) {
  const [state, action, pending] = useActionState(bootstrapItemAction, initialState);
  return (
    <form action={action}>
      <input type="hidden" name="item_id" value={itemId} />
      <Message state={state} />
      <button className="button button-primary" type="submit" disabled={pending}>
        {pending ? "正在重新检查" : "重新执行确定性引导检查"}
      </button>
    </form>
  );
}
