"use server";

import { revalidatePath } from "next/cache";
import { humanTestFetch, LocalHumanTestApiError } from "../../../lib/local-human-test";
import { investigationLoginHelp, type InvestigationRuntime } from "../../../lib/investigation-runtime";

export async function runtimeAction(_state: { error: string | null }, form: FormData): Promise<{ error: string | null; message?: string; result?: InvestigationRuntime }> {
  const operation = form.get("operation");
  if (!["save", "check", "refresh"].includes(String(operation))) return { error: "请选择配置或检查操作。" };
  try {
    if (operation === "save") {
      const apiKey = String(form.get("api_key") ?? "").trim();
      const agentId = String(form.get("agent_id") ?? "").trim();
      const sourceApp = String(form.get("source_app") ?? "").trim();
      if (!apiKey || apiKey.length > 4096 || /\s/.test(apiKey) || !/^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/.test(agentId) || !/^[A-Za-z0-9_.:-]{1,128}$/.test(sourceApp)) return { error: "请填写有效的 WMA 密钥、Agent 标识和调用方。" };
      await humanTestFetch("/investigation-runtime/configuration", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ api_key: apiKey, agent_id: agentId, source_app: sourceApp }) });
    } else if (operation === "check") {
      await humanTestFetch("/investigation-runtime/check", { method: "POST" });
    }
    const result = await humanTestFetch<InvestigationRuntime>("/investigation-runtime");
    revalidatePath("/review/investigations");
    return { error: null, result, message: operation === "save" ? "配置已安全保存，请检查发布连接。" : "就绪状态已更新。" };
  } catch (error) {
    return { error: error instanceof LocalHumanTestApiError && [401, 403].includes(error.status)
      ? investigationLoginHelp : "操作未完成。请检查服务与 WMA 配置后重试；不会自动发起调查。" };
  }
}
