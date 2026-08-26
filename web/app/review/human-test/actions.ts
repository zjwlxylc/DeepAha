"use server";

import { randomUUID } from "node:crypto";

import { revalidatePath } from "next/cache";

import { humanTestFetch } from "../../../lib/local-human-test";

export interface HumanTestActionState {
  error: string | null;
  message: string | null;
}

const UUID_V7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function text(formData: FormData, key: string): string {
  return String(formData.get(key) ?? "").trim();
}

function actionHeaders(): HeadersInit {
  return {
    "Content-Type": "application/json",
    "Idempotency-Key": randomUUID(),
  };
}

async function mutate(
  path: string,
  init: RequestInit,
  success: string,
): Promise<HumanTestActionState> {
  try {
    await humanTestFetch(path, init);
  } catch {
    return {
      error: "操作未完成。请核对当前阶段、权限和证据后重试。",
      message: null,
    };
  }
  revalidatePath("/review/human-test");
  return { error: null, message: success };
}

export async function saveProviderConfigAction(
  _state: HumanTestActionState,
  formData: FormData,
): Promise<HumanTestActionState> {
  const baseUrl = text(formData, "base_url");
  const apiKey = text(formData, "api_key");
  let parsed: URL;
  try {
    parsed = new URL(baseUrl);
  } catch {
    return { error: "请填写有效的 HTTPS Provider 地址。", message: null };
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    !apiKey
  ) {
    return { error: "请填写有效的 HTTPS Provider 地址和 API Key。", message: null };
  }
  const body = {
    provider: text(formData, "provider"),
    base_url: baseUrl,
    protocol: text(formData, "protocol"),
    model_id: text(formData, "model_id"),
    model_snapshot: text(formData, "model_snapshot"),
    provider_region: text(formData, "provider_region"),
    zero_retention: formData.get("zero_retention") === "on",
    training_use: false,
    supports_idempotency: formData.get("supports_idempotency") === "on",
    api_key: apiKey,
  };
  if (
    !body.provider ||
    body.protocol !== "openai_chat_completions" ||
    !body.model_id ||
    !body.model_snapshot ||
    !body.provider_region
  ) {
    return { error: "请完整填写受控 Provider 字段。", message: null };
  }
  return mutate(
    "/config/provider",
    { method: "PUT", headers: actionHeaders(), body: JSON.stringify(body) },
    "Provider 配置已安全保存。",
  );
}

export async function deleteProviderSecretAction(
  _state: HumanTestActionState,
  _formData: FormData,
): Promise<HumanTestActionState> {
  void _state;
  void _formData;
  return mutate(
    "/config/provider/secret",
    { method: "DELETE", headers: actionHeaders() },
    "Provider 密钥已删除，真实模型调用已关闭。",
  );
}

export async function createHumanTestRunAction(
  _state: HumanTestActionState,
  formData: FormData,
): Promise<HumanTestActionState> {
  const mode = text(formData, "mode");
  const recipeIds = formData.getAll("recipe_id").map(String).filter((id) => UUID_V7.test(id));
  const confirmed = formData.get("confirm_live_official") === "on";
  if (
    !["LIVE_OFFICIAL", "OFFICIAL_REPLAY"].includes(mode) ||
    recipeIds.length === 0
  ) {
    return { error: "请选择至少一个已审核来源。", message: null };
  }
  if (mode === "LIVE_OFFICIAL" && !confirmed) {
    return { error: "开始真实运行前必须确认来源与硬预算。", message: null };
  }
  return mutate(
    "/runs",
    {
      method: "POST",
      headers: actionHeaders(),
      body: JSON.stringify({
        mode,
        recipe_ids: recipeIds,
        confirm_live_official: confirmed,
        budget: {
          official_request_limit: 9,
          llm_call_limit: 8,
          max_input_tokens: 12000,
          max_output_tokens: 3000,
          timeout_seconds: 90,
          temperature: 0,
        },
      }),
    },
    mode === "LIVE_OFFICIAL" ? "受控真实运行已创建。" : "离线回放已创建。",
  );
}

export async function cancelHumanTestRunAction(
  _state: HumanTestActionState,
  formData: FormData,
) {
  const runId = text(formData, "run_id");
  if (!UUID_V7.test(runId)) return { error: "运行不可用。", message: null };
  return mutate(
    `/runs/${runId}/cancel`,
    { method: "POST", headers: actionHeaders() },
    "已请求停止该运行。",
  );
}

export async function bootstrapItemAction(
  _state: HumanTestActionState,
  formData: FormData,
) {
  const itemId = text(formData, "item_id");
  if (!UUID_V7.test(itemId)) return { error: "条目不可用。", message: null };
  return mutate(
    `/items/${itemId}/bootstrap`,
    { method: "POST", headers: actionHeaders() },
    "确定性引导检查已完成。",
  );
}

export async function decideFactAction(
  _state: HumanTestActionState,
  formData: FormData,
): Promise<HumanTestActionState> {
  const itemId = text(formData, "item_id");
  const candidateId = text(formData, "candidate_id");
  const decision = text(formData, "decision");
  const reason = text(formData, "reason");
  if (
    !UUID_V7.test(itemId) ||
    !UUID_V7.test(candidateId) ||
    !["APPROVE", "REJECT", "UNKNOWN"].includes(decision) ||
    !reason ||
    reason.length > 500
  ) {
    return { error: "请完整填写事实审核决定和理由。", message: null };
  }
  return mutate(
    `/items/${itemId}/facts/decision`,
    {
      method: "POST",
      headers: actionHeaders(),
      body: JSON.stringify({ candidate_id: candidateId, decision, reason }),
    },
    "事实审核决定已记录。",
  );
}

export async function decideRuleAction(
  _state: HumanTestActionState,
  formData: FormData,
): Promise<HumanTestActionState> {
  const itemId = text(formData, "item_id");
  const candidateId = text(formData, "rule_candidate_id");
  const decision = text(formData, "decision");
  const reason = text(formData, "reason");
  if (
    !UUID_V7.test(itemId) ||
    !UUID_V7.test(candidateId) ||
    !["APPROVE", "REJECT", "NEEDS_ADJUDICATION"].includes(decision) ||
    !reason ||
    reason.length > 500
  ) {
    return { error: "请完整填写规则审核决定和理由。", message: null };
  }
  return mutate(
    `/items/${itemId}/rules/decision`,
    {
      method: "POST",
      headers: actionHeaders(),
      body: JSON.stringify({ rule_candidate_id: candidateId, decision, reason }),
    },
    "规则审核决定已记录。",
  );
}

export async function publishItemAction(
  _state: HumanTestActionState,
  formData: FormData,
) {
  const itemId = text(formData, "item_id");
  if (!UUID_V7.test(itemId)) return { error: "条目不可用。", message: null };
  return mutate(
    `/items/${itemId}/publish`,
    { method: "POST", headers: actionHeaders() },
    "已发布到本地人工审核目录。",
  );
}
