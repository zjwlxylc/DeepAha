"use client";

import { useActionState } from "react";

import { publishItemAction, type HumanTestActionState } from "../../app/review/human-test/actions";
import type { PublicationPreview } from "../../lib/local-human-test";

const initialState: HumanTestActionState = { error: null, message: null };

export default function PublicationPreviewPanel({ itemId, preview }: { itemId: string; preview: PublicationPreview | null }) {
  const [state, action, pending] = useActionState(publishItemAction, initialState);
  return (
    <section className="human-test-panel" aria-labelledby="publication-title">
      <h2 id="publication-title">本地发布预览</h2>
      {!preview ? <p>事实尚未完成独立人工审核，当前不能生成发布预览。</p> : (
        <>
          <dl className="compact-facts">
            <div><dt>数据标签</dt><dd>LOCAL_HUMAN_REVIEWED</dd></div>
            <div><dt>资格上限</dt><dd>{preview.eligibility_ceiling}</dd></div>
            <div><dt>内容使用依据</dt><dd>{preview.content_use_basis ?? "未满足"}</dd></div>
            <div><dt>官方证据</dt><dd>{preview.official_evidence_complete ? "完整" : "不完整"}</dd></div>
          </dl>
          {preview.blocker_codes.length ? (
            <ul className="form-alert" aria-label="发布阻断原因">
              {preview.blocker_codes.map((code) => <li key={code}>{code}</li>)}
            </ul>
          ) : null}
          <form action={action}>
            <input type="hidden" name="item_id" value={itemId} />
            {state.error ? <p className="form-alert" role="alert">{state.error}</p> : null}
            {state.message ? <p className="form-success" role="status">{state.message}</p> : null}
            <button className="button button-primary" type="submit" disabled={!preview.eligible || pending}>
              {pending ? "正在发布" : "确认发布到本地机会库"}
            </button>
          </form>
        </>
      )}
    </section>
  );
}
