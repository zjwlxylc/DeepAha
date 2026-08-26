"use client";

import { useActionState, useState } from "react";

import {
  createHumanTestRunAction,
  type HumanTestActionState,
} from "../../app/review/human-test/actions";
import type { LocalSource } from "../../lib/local-human-test";

const initialState: HumanTestActionState = { error: null, message: null };

export default function RunForm({
  sources,
  providerReady,
}: {
  sources: LocalSource[];
  providerReady: boolean;
}) {
  const [mode, setMode] = useState<"OFFICIAL_REPLAY" | "LIVE_OFFICIAL">("OFFICIAL_REPLAY");
  const [confirmed, setConfirmed] = useState(false);
  const [state, action, pending] = useActionState(createHumanTestRunAction, initialState);
  const live = mode === "LIVE_OFFICIAL";
  return (
    <section className="human-test-panel" aria-labelledby="create-run-title">
      <div className="human-test-panel-heading">
        <div>
          <p className="section-kicker">Explicit side effects</p>
          <h2 id="create-run-title">新建受控运行</h2>
        </div>
        <span className="status-badge">串行 worker</span>
      </div>
      <form className="human-test-form" action={action}>
        <fieldset className="human-test-fieldset">
          <legend>运行模式</legend>
          <label className="check-label">
            <input
              type="radio"
              name="mode"
              value="OFFICIAL_REPLAY"
              checked={!live}
              onChange={() => { setMode("OFFICIAL_REPLAY"); setConfirmed(false); }}
            />
            离线官方回放（不访问官网）
          </label>
          <label className="check-label">
            <input
              type="radio"
              name="mode"
              value="LIVE_OFFICIAL"
              checked={live}
              onChange={() => { setMode("LIVE_OFFICIAL"); setConfirmed(false); }}
            />
            受控实时采集（访问所选官方公开地址并调用 Provider）
          </label>
        </fieldset>
        <fieldset className="human-test-fieldset">
          <legend>已审核来源</legend>
          <div className="source-choice-list">
            {sources.map((source) => (
              <label className="source-choice" key={source.recipe_id}>
                <input type="checkbox" name="recipe_id" value={source.recipe_id} defaultChecked />
                <span>
                  <strong>{source.authority_name}</strong>
                  <small>{source.official_host} · {source.usage_role} · 单 Recipe 上限 {source.maximum_requests}</small>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <dl className="budget-grid" aria-label="不可变硬预算">
          <div><dt>官方请求</dt><dd>≤ 9</dd></div>
          <div><dt>LLM 调用</dt><dd>≤ 8</dd></div>
          <div><dt>输入 token</dt><dd>≤ 12,000</dd></div>
          <div><dt>输出 token</dt><dd>≤ 3,000</dd></div>
          <div><dt>单次超时</dt><dd>≤ 90 秒</dd></div>
          <div><dt>temperature</dt><dd>0</dd></div>
        </dl>
        {live ? (
          <label className="live-confirmation">
            <input
              type="checkbox"
              name="confirm_live_official"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            确认来源与硬预算；本次会访问官方公开站点并消耗真实 Provider 配额。
          </label>
        ) : null}
        {state.error ? <p className="form-alert" role="alert">{state.error}</p> : null}
        {state.message ? <p className="form-success" role="status">{state.message}</p> : null}
        <button
          className="button button-primary"
          type="submit"
          disabled={!providerReady || pending || (live && !confirmed) || sources.length === 0}
        >
          {pending
            ? "正在创建"
            : live
              ? "开始受控真实运行"
              : "开始离线官方回放"}
        </button>
        {!providerReady ? <p className="field-help">先完成可出站的 Provider 配置。</p> : null}
      </form>
    </section>
  );
}
