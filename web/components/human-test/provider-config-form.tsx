"use client";

import { useActionState, useState } from "react";

import {
  deleteProviderSecretAction,
  saveProviderConfigAction,
  type HumanTestActionState,
} from "../../app/review/human-test/actions";
import type { ProviderStatus } from "../../lib/local-human-test";

const initialState: HumanTestActionState = { error: null, message: null };

const providerPresets = {
  "agnes-2.5-flash": {
    provider: "agnes",
    baseUrl: "https://apihub.agnes-ai.com/v1",
    modelId: "agnes-2.5-flash",
    modelSnapshot: "agnes-2.5-flash@catalog-2026-07-30",
    providerRegion: "global",
  },
  "deepseek-v4-flash": {
    provider: "deepseek",
    baseUrl: "https://api.deepseek.com",
    modelId: "deepseek-v4-flash",
    modelSnapshot: "DeepSeek-V4-Flash-0731",
    providerRegion: "cn",
  },
  "deepseek-v4-pro": {
    provider: "deepseek",
    baseUrl: "https://api.deepseek.com",
    modelId: "deepseek-v4-pro",
    modelSnapshot: "DeepSeek-V4-Pro",
    providerRegion: "cn",
  },
} as const;

type ProviderPreset = keyof typeof providerPresets;

function ActionMessage({ state }: { state: HumanTestActionState }) {
  if (state.error) return <p className="form-alert" role="alert">{state.error}</p>;
  if (state.message) return <p className="form-success" role="status">{state.message}</p>;
  return null;
}

export default function ProviderConfigForm({ status }: { status: ProviderStatus }) {
  const initialPreset: ProviderPreset = "agnes-2.5-flash";
  const initial = status.configured
    ? {
        provider: status.provider ?? "",
        baseUrl: status.base_url ?? "",
        modelId: status.model_id ?? "",
        modelSnapshot: status.model_snapshot ?? "",
        providerRegion: status.provider_region ?? "unknown",
      }
    : providerPresets[initialPreset];
  const [preset, setPreset] = useState<ProviderPreset | "custom">(
    status.configured ? "custom" : initialPreset,
  );
  const [fields, setFields] = useState(initial);
  const [saveState, saveAction, savePending] = useActionState(
    saveProviderConfigAction,
    initialState,
  );
  const [deleteState, deleteAction, deletePending] = useActionState(
    deleteProviderSecretAction,
    initialState,
  );
  function selectPreset(value: ProviderPreset | "custom") {
    setPreset(value);
    if (value !== "custom") setFields(providerPresets[value]);
  }
  function updateField(name: keyof typeof fields, value: string) {
    setPreset("custom");
    setFields((current) => ({ ...current, [name]: value }));
  }
  const statusLabel = status.egress_ready
    ? "已保存，可真实运行"
    : status.configured
      ? "已保存，待确认数据政策"
      : "尚未配置";
  return (
    <section className="human-test-panel" aria-labelledby="provider-config-title">
      <div className="human-test-panel-heading">
        <div>
          <p className="section-kicker">Provider boundary</p>
          <h2 id="provider-config-title">模型 Provider 配置</h2>
        </div>
        <span className={`status-badge ${status.egress_ready ? "status-open" : "status-closed"}`}>
          {statusLabel}
        </span>
      </div>
      <p className="field-help">
        密钥只写入当前 Windows 用户的 DPAPI 加密文件。保存后页面、API、数据库和日志都不会回显。
      </p>
      <form className="human-test-form" action={saveAction}>
        <div className="human-test-form-grid">
          <label>
            快速选择公开配置
            <select
              value={preset}
              onChange={(event) => selectPreset(event.target.value as ProviderPreset | "custom")}
            >
              <option value="agnes-2.5-flash">Agnes 2.5 Flash</option>
              <option value="deepseek-v4-flash">DeepSeek V4 Flash</option>
              <option value="deepseek-v4-pro">DeepSeek V4 Pro</option>
              <option value="custom">自定义</option>
            </select>
          </label>
          <label>
            Provider 名称
            <input
              name="provider"
              value={fields.provider}
              onChange={(event) => updateField("provider", event.target.value)}
              required
            />
          </label>
          <label>
            HTTPS Base URL
            <input
              name="base_url"
              type="url"
              value={fields.baseUrl}
              onChange={(event) => updateField("baseUrl", event.target.value)}
              required
            />
          </label>
          <label>
            协议
            <select name="protocol" defaultValue={status.protocol ?? "openai_chat_completions"}>
              <option value="openai_chat_completions">OpenAI Chat Completions compatible</option>
            </select>
          </label>
          <label>
            模型 ID
            <input
              name="model_id"
              value={fields.modelId}
              onChange={(event) => updateField("modelId", event.target.value)}
              required
            />
          </label>
          <label>
            模型快照
            <input
              name="model_snapshot"
              value={fields.modelSnapshot}
              onChange={(event) => updateField("modelSnapshot", event.target.value)}
              required
            />
          </label>
          <label>
            Provider 区域
            <input
              name="provider_region"
              value={fields.providerRegion}
              onChange={(event) => updateField("providerRegion", event.target.value)}
              required
            />
          </label>
          <label className="human-test-secret-field">
            API Key（保存后保持空白）
            <input name="api_key" type="password" autoComplete="new-password" required />
          </label>
        </div>
        <div className="human-test-checks">
          <label className="check-label">
            <input
              name="no_training_use_confirmed"
              type="checkbox"
              defaultChecked={status.training_use === false}
            />
            已在 Provider 设置或合同中确认：本次输入不用于模型训练
          </label>
          <label className="check-label">
            <input name="zero_retention" type="checkbox" defaultChecked={status.zero_retention ?? false} />
            Provider 已额外确认零保留（zero retention，可选）
          </label>
          <label className="check-label">
            <input
              name="supports_idempotency"
              type="checkbox"
              defaultChecked={status.supports_idempotency ?? false}
            />
            Provider 已确认支持幂等请求身份（可选）
          </label>
        </div>
        <p className="field-help">
          本地真实运行只发送已审核官方公开证据。零保留和幂等能力没有书面依据时请保持未选；
          “不用于模型训练”必须先在 Provider 设置或合同中确认。
        </p>
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
