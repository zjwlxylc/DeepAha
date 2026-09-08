"use server";

import { postInvestigation } from "../../../lib/investigations";
import { LocalHumanTestApiError } from "../../../lib/local-human-test";
import type { InvestigationUnitSnapshot } from "../../../lib/unit-snapshots";

export interface UnitPlanActionState { error: string | null; planId: string | null }
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function prepareUnitPlanAction(_state: UnitPlanActionState, form: FormData): Promise<UnitPlanActionState> {
  const value = (key: string) => String(form.get(key) ?? "").trim();
  const ids = ["task_id", "binding_id", "check_id", "fact_preparation_id", "fact_set_id", "rule_preparation_id"];
  if (ids.some(key => !UUID.test(value(key))) || !/^[a-f0-9]{64}$/.test(value("delivery_hash"))
    || !value("entity_id") || value("entity_id").length > 256) {
    return { error: "当前材料、核验回执或审核版本不完整，请刷新任务后核对。", planId: null };
  }
  const body = Object.fromEntries([...ids.slice(1), "delivery_hash", "entity_id"].map(key => [key, value(key)]));
  try {
    const snapshot = await postInvestigation<InvestigationUnitSnapshot>(`/investigations/${value("task_id")}/unit-plans`, body, value("request_key"));
    if (!UUID.test(snapshot.plan_id)) throw new Error("Invalid snapshot identity");
    return { error: null, planId: snapshot.plan_id };
  } catch (error) {
    const message = error instanceof LocalHumanTestApiError && [401, 403].includes(error.status)
      ? "当前审核身份没有操作权限，请使用已授权的审核会话。"
      : error instanceof LocalHumanTestApiError && error.status === 409
        ? "当前证据、版本或规则决定尚不满足快照要求，请刷新任务并核对待处理项。"
        : "暂未取得快照回执。可保留当前输入重试，已有快照会复用。";
    return { error: message, planId: null };
  }
}
