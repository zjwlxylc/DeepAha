"use server";
import { humanTestFetch, LocalHumanTestApiError } from "../../../lib/local-human-test";
import { scopeUuid, validScopePreflight, type ScopePreflightView } from "../../../lib/scope-preflight";
import type { RelationResult } from "../../../lib/relation-review";
export async function loadScopePreflight(task: string, plan: string): Promise<RelationResult<ScopePreflightView>> {
  try {
    if (![task, plan].every(id => scopeUuid.test(id))) throw new Error("Invalid identity");
    const value = await humanTestFetch<ScopePreflightView>(`/investigations/${task}/unit-plans/${plan}/scope-preflight`);
    if (!validScopePreflight(value, task, plan)) throw new Error("Invalid preflight");
    return { ok: true, value };
  } catch (error) {
    const reason = error instanceof LocalHumanTestApiError && [401, 403].includes(error.status)
      ? "当前会话没有查看权限，请使用已授权的审核会话。"
      : error instanceof LocalHumanTestApiError && error.status === 409
        ? "当前来源已变化或无法取得完整预检，请返回任务核对。"
        : "当前预检读取失败，请重试或返回任务核对。";
    return { ok: false, error: `${reason}旧结果已隐藏。` };
  }
}
