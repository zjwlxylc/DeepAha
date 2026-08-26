"use client";

import { useActionState } from "react";

import {
  deleteProviderSecretAction,
  saveProviderConfigAction,
  type HumanTestActionState,
} from "../../app/review/human-test/actions";
import type { ProviderStatus } from "../../lib/local-human-test";

const initialState: HumanTestActionState = { error: null, message: null };

function ActionMessage({ state }: { state: HumanTestActionState }) {
  if (state.error) return <p className="form-alert" role="alert">{state.error}</p>;
  if (state.message) return <p className="form-success" role="status">{state.message}</p>;
  return null;
}

export default function ProviderConfigForm({ status }: { status: ProviderStatus }) {
  const [saveState, saveAction, savePending] = useActionState(
    saveProviderConfigAction,
    initialState,
  );
  const [deleteState, deleteAction, deletePending] = useActionState(
    deleteProviderSecretAction,
    initialState,
  );
  return (
    <section className="human-test-panel" aria-labelledby="provider-config-title">
      <div className="human-test-panel-heading">
        <div>
          <p className="section-kicker">Provider boundary</p>
          <h2 id="provider-config-title">模型 Provider 配置</h2>
        </div>
        <span className={`status-badge ${status.egress_ready ? "status-open" : "status-closed"}`}>
          {status.configured ? "已安全保存" : "尚未配置"}
        </span>
      </div>
      <p className="field-help">
        密钥只写入当前 Windows 用户的 DPAPI 加密文件。保存后页面、API、数据库和日志都不会回显。
      </p>
      <form className="human-test-form" action={saveAction}>
        <div className="human-test-form-grid">
          <label>
            Provider 名称
            <input name="provider" defaultValue={status.provider ?? "agnes"} required />
          </label>
          <label>
            HTTPS Base URL
            <input name="base_url" type="url" defaultValue={status.base_url ?? ""} required />
          </label>
          <label>
            协议
            <select name="protocol" defaultValue={status.protocol ?? "openai_chat_completions"}>
              <option value="openai_chat_completions">OpenAI Chat Completions compatible</option>
            </select>
          </label>
          <label>
            模型 ID
            <input name="model_id" defaultValue={status.model_id ?? ""} required />
          </label>
          <label>
            模型快照
            <input name="model_snapshot" defaultValue={status.model_snapshot ?? ""} required />
          </label>
          <label>
            Provider 区域
            <input name="provider_region" defaultValue={status.provider_region ?? "cn"} required />
          </label>
          <label className="human-test-secret-field">
            API Key（保存后保持空白）
            <input name="api_key" type="password" autoComplete="new-password" required />
          </label>
        </div>
        <div className="human-test-checks">
          <label className="check-label">
            <input name="zero_retention" type="checkbox" defaultChecked={status.zero_retention ?? true} />
            Provider 已确认零保留（zero retention）
          </label>
          <label className="check-label">
            <input
              name="supports_idempotency"
              type="checkbox"
              defaultChecked={status.supports_idempotency ?? true}
            />
            Provider 支持幂等请求身份
          </label>
        </div>
        <ActionMessage state={saveState} />
        <button className="button button-primary" type="submit" disabled={savePending}>
          {savePending ? "正在安全保存" : "保存 Provider 配置"}
        </button>
      </form>
      {status.configured ? (
        <form className="human-test-danger-row" action={deleteAction}>
          <p>删除密钥会立即关闭后续真实模型调用，但保留非敏感配置和既有审计记录。</p>
          <ActionMessage state={deleteState} />
          <button className="button button-danger" type="submit" disabled={deletePending}>
            {deletePending ? "正在删除" : "删除已保存密钥"}
          </button>
        </form>
      ) : null}
    </section>
  );
}
