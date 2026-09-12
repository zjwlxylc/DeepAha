export interface InvestigationRuntime {
  login: string;
  database: string;
  source_count: number;
  worker: { state: string; updated_at?: string | null };
  wma: { state: string; sdk_available?: boolean; agent_id?: string; source_app?: string;
    revision?: string; checked_at?: string; error_code?: string;
    release?: { published_model?: string; release_version?: string } | null };
  dispatch_enabled: boolean;
}

export const wmaStates: Record<string, string> = {
  NOT_CONFIGURED: "未配置", SAVED: "已保存，尚未检查连接", CONNECTION_VERIFIED: "发布连接已验证",
  CHECK_FAILED: "连接检查失败", CHECK_EXPIRED: "连接检查已过期", UNREADABLE: "配置无法读取",
};

export const investigationLoginHelp = "当前浏览器没有有效审核会话。请使用一键启动入口打开的浏览器；Codex 内置浏览器及其他浏览器不会共享该登录。会话失效时，请停止后重新启动本地体验。";

/**
 * Explains whether the explicit "发起调查" control is currently available.
 * `dispatch_enabled` is the authoritative boolean (worker RUNNING ∧ WMA
 * CONNECTION_VERIFIED ∧ source_count > 0) computed by the backend; when it is
 * false we still surface *why* so the operator knows what to fix — in
 * particular an expired connection check, which must be re-checked manually
 * (the page never triggers a check on load).
 */
export function dispatchReadiness(runtime: InvestigationRuntime): { ready: boolean; message: string } {
  if (runtime.dispatch_enabled) return { ready: true, message: "已就绪：可以在调查任务上发起调查。" };
  if (runtime.wma.state === "CHECK_EXPIRED") return { ready: false, message: "连接检查已过期，请重新检查后再发起调查。" };
  if (runtime.wma.state !== "CONNECTION_VERIFIED") return { ready: false, message: "WMA 发布连接尚未验证，暂时不能发起调查。" };
  if (runtime.worker.state !== "RUNNING") return { ready: false, message: "调查处理进程未运行，暂时不能发起调查。" };
  if (runtime.source_count <= 0) return { ready: false, message: "暂无可用来源，暂时不能发起调查。" };
  return { ready: false, message: "当前不满足发起条件，暂时不能发起调查。" };
}
