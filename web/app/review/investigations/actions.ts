"use server";

import { createHash } from "node:crypto";
import { revalidatePath } from "next/cache";

import { getInvestigationSources, InvestigationApiError, postInvestigation } from "../../../lib/investigations";
import { LocalHumanTestApiError } from "../../../lib/local-human-test";

export interface InvestigationActionState {
  error: string | null;
  message: string | null;
  taskId: string | null;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256 = /^[0-9a-f]{64}$/;

function text(form: FormData, key: string): string {
  return String(form.get(key) ?? "").trim();
}

function lines(form: FormData, key: string): string[] {
  return Array.from(new Set(text(form, key).split(/\r?\n/).map((line) => line.trim()).filter(Boolean)));
}

function publicUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return /^https:\/\/[^/]/i.test(value) && url.protocol === "https:" && ["", "443"].includes(url.port)
      && !url.username && !url.password && !url.hash && !/[\\\s]/.test(value);
  } catch {
    return false;
  }
}

function invalid(message: string): InvestigationActionState {
  return { error: message, message: null, taskId: null };
}

function failure(error: unknown, registration: boolean): InvestigationActionState {
  if (error instanceof LocalHumanTestApiError && [401, 403].includes(error.status)) {
    return invalid("当前审核身份没有操作权限。请使用已授权的真人审核会话。");
  }
  if (error instanceof LocalHumanTestApiError && error.status === 409) {
    if (registration) {
      const messages: Record<string, string> = {
        APPROVED_SOURCE_REQUIRED: "所选来源当前未获批准。请刷新来源列表后重新选择。",
        NOTICE_OUTSIDE_APPROVED_HOSTS: "公告和附件地址必须使用所选来源已批准的域名。请核对地址或重新选择来源。",
        IDEMPOTENCY_CONFLICT: "登记请求发生重复冲突。请先查看任务列表，确认是否已登记。",
      };
      return invalid((error instanceof InvestigationApiError && error.code && messages[error.code])
        || "登记未完成。请刷新来源列表并核对登记内容后重试。");
    }
    return invalid("任务状态或材料版本已变化。请刷新详情后重新核对。");
  }
  return invalid("操作未完成。请核对来源、任务状态和材料后重试。");
}

async function submit(path: string, body: object, requestKey: string, message: string): Promise<InvestigationActionState> {
  if (!UUID.test(requestKey)) return invalid("表单已失效，请刷新页面后重新填写。");
  // The form identity exists before the first POST, so a lost API/action response
  // can be replayed. Changed content is a different intent, not a conflicting retry.
  const key = createHash("sha256").update(JSON.stringify([requestKey, path, body])).digest("hex");
  try {
    const task = await postInvestigation(path, body, key);
    revalidatePath("/review/investigations");
    revalidatePath(`/review/investigations/${task.task_id}`);
    return { error: null, message, taskId: task.task_id };
  } catch (error) {
    return failure(error, path === "/investigations");
  }
}

export async function createInvestigationAction(
  _state: InvestigationActionState,
  form: FormData,
): Promise<InvestigationActionState> {
  const [sourceId, endpointId, extra] = text(form, "source_key").split("/");
  const noticeUrl = text(form, "notice_url");
  const brief = text(form, "brief");
  const wallTimeSeconds = Number(text(form, "wall_time_seconds"));
  const artifactUrls = lines(form, "expected_artifact_urls");
  const entityKeys = lines(form, "expected_entity_keys");
  if (!UUID.test(sourceId ?? "") || !UUID.test(endpointId ?? "") || extra !== undefined) {
    return invalid("请选择已批准的官方来源。");
  }
  if (!publicUrl(noticeUrl) || artifactUrls.some((url) => !publicUrl(url))) {
    return invalid("请使用 HTTPS 官方网页或附件地址，端口仅限 443，不包含账号、密码、空白或页面锚点。");
  }
  if (!brief || brief.length > 12000) return invalid("调查说明需填写 1–12000 个字符。");
  if (!Number.isInteger(wallTimeSeconds) || wallTimeSeconds < 60 || wallTimeSeconds > 1800) {
    return invalid("执行时间上限需为 60–1800 秒的整数。");
  }
  try {
    const { sources } = await getInvestigationSources();
    const selected = sources.find((source) => source.source_id === sourceId && source.endpoint_id === endpointId);
    if (!selected) return invalid("所选来源当前未获批准。请刷新来源列表后重新选择。");
    if ([noticeUrl, ...artifactUrls].some((url) => !selected.allowed_hosts.includes(new URL(url).hostname))) {
      return invalid("公告和附件地址必须使用所选来源已批准的域名。请核对地址或重新选择来源。");
    }
  } catch (error) { return failure(error, true); }
  return submit("/investigations", {
    source_id: sourceId, endpoint_id: endpointId, notice_url: noticeUrl, brief,
    expected_artifact_urls: artifactUrls, expected_entity_keys: entityKeys,
    calibration: form.get("calibration") === "on", wall_time_seconds: wallTimeSeconds,
  }, text(form, "request_key"), "调查任务已登记，后续由获授权的运维人员安排执行。");
}

export async function reviewInvestigationAction(
  _state: InvestigationActionState,
  form: FormData,
): Promise<InvestigationActionState> {
  const taskId = text(form, "task_id");
  const deliveryHash = text(form, "delivery_hash");
  const decision = text(form, "decision");
  const reason = text(form, "reason");
  if (!UUID.test(taskId) || !SHA256.test(deliveryHash)) return invalid("当前任务或材料版本不可审核，请刷新详情。");
  if (!["APPROVE", "REJECT"].includes(decision) || !reason || reason.length > 2000) {
    return invalid("请选择审核决定，并填写 1–2000 个字符的核对理由。");
  }
  return submit(`/investigations/${taskId}/review`, {
    decision, delivery_hash: deliveryHash, reason,
  }, text(form, "request_key"), "内部材料审核已记录；正式机会与资格规则尚未发布。");
}
