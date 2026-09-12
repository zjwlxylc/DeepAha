"use server";

import { createHash } from "node:crypto";
import { revalidatePath } from "next/cache";

import { getInvestigationSources, InvestigationApiError, postInvestigation } from "../../../lib/investigations";
import { investigationDispatchPath } from "../../../lib/investigation-dispatch";
import { LocalHumanTestApiError } from "../../../lib/local-human-test";
import { investigationLoginHelp } from "../../../lib/investigation-runtime";
import { isExplicitRuleTime, ruleAuthorities, ruleRelations, ruleApplicability, ruleDecisions } from "../../../lib/investigation-rule-options";

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

function failure(error: unknown, registration: boolean, loginMessage = "当前审核身份没有操作权限。请使用已授权的真人审核会话。"): InvestigationActionState {
  if (error instanceof LocalHumanTestApiError && [401, 403].includes(error.status)) {
    return invalid(loginMessage);
  }
  if (error instanceof LocalHumanTestApiError && error.status === 409) {
    const identityMessages: Record<string, string> = {
      RULE_EVIDENCE_REVIEW_INCOMPLETE: "请逐条核对本规则的全部证据。批准需要明确权威级别、支持关系、生效时间及精确适用目标。",
      RULE_NOT_EXECUTABLE: "该候选尚不能编译为可执行规则，请保留待裁决并核对条件。",
      RULE_CANDIDATE_ALREADY_DECIDED: "该规则已经有最终决定，请刷新查看审核记录。",
      FACT_EVIDENCE_CHECK_REFRESH_REQUIRED: "核验版本已变化，请重新准备文档证据，再整理字段候选。旧审核记录会保留。",
      FACT_BINDING_DOCUMENTS_CHANGED: "当前解析版本与已确认来源不一致，请先重新确认材料归属。",
      FACT_ALL_CANDIDATES_REQUIRE_DECISION: "此目标仍有候选字段尚未作出决定，或存在待裁决项。请先逐项核对。",
      REGISTRATION_EXISTING_IDENTITY_OR_REVIEW_REQUIRED: "检测到已有身份或可能重复的机会。请核对已有机会并使用关联入口；身份不明确时需先核对。",
      REGISTRATION_POSITION_INVALID: "岗位重复、已关联或属于单位分组，请核对勾选项。",
      REGISTRATION_POSITION_KEY_CONFLICT: "内部岗位识别键已被使用，请核对已有岗位并关联，或修正识别键。",
      TASK_NOT_DISPATCHABLE: "本任务当前不在可发起状态（可能已被处理或状态已变化）。请刷新详情后核对。",
      TASK_ALREADY_RUNNING: "已有一个执行中的租约，暂时无需重复发起。请稍后刷新详情查看进度。",
      // Document exclusion: each code names the one thing the operator can still
      // do, so a rejected exclusion never falls back to a generic refresh hint.
      DOCUMENT_EXCLUSION_REASON_REQUIRED: "排除或撤销理由需填写 8–2000 个字符，请补充具体依据后重新提交。",
      DOCUMENT_EXCLUSION_NOT_UNSUPPORTED: "只有「格式尚不支持」的材料才能排除；此材料当前状态不允许排除，请刷新后核对材料状态。",
      DOCUMENT_EXCLUSION_NOT_ALLOWED: "当前任务状态不允许排除或撤销材料，请刷新详情并确认任务仍待处理或已批准。",
      DOCUMENT_EXCLUSION_ALREADY_PRESENT: "此材料已经排除过，无需重复排除；如需恢复解析，请改用「撤销排除」。",
      DOCUMENT_EXCLUSION_NOT_FOUND: "没有找到可撤销的排除记录，该材料可能已恢复解析；请刷新详情后确认。",
      DOCUMENT_EXCLUSION_DELIVERY_CONFLICT: "材料版本已变化，请刷新详情后重新排除或撤销。",
      DOCUMENT_EXCLUSION_MATERIAL_NOT_FOUND: "找不到该材料，它可能已不在本次回收结果中；请刷新详情后核对材料清单。",
    };
    if (error instanceof InvestigationApiError && error.code && identityMessages[error.code]) return invalid(identityMessages[error.code]);
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

async function submit(path: string, body: object, requestKey: string, message: string, loginMessage?: string): Promise<InvestigationActionState> {
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
    return failure(error, path === "/investigations", loginMessage);
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

export async function prepareInvestigationDocumentsAction(
  _state: InvestigationActionState,
  form: FormData,
): Promise<InvestigationActionState> {
  const taskId = text(form, "task_id");
  const deliveryHash = text(form, "delivery_hash");
  if (!UUID.test(taskId) || !SHA256.test(deliveryHash)) return invalid("当前任务或材料版本不可准备，请刷新详情。");
  return submit(`/investigations/${taskId}/documents`, { delivery_hash: deliveryHash },
    text(form, "request_key"),
    "文档准备结果已更新，请逐项查看未支持或需复核的材料；事实仍待人工审核。");
}

/**
 * Hands one material to the opaque parser. The material keeps a document so the
 * flow can advance, but no block carries quotable text — so it must never back a
 * block-level field decision. That boundary is repeated in the success copy.
 */
export async function excludeInvestigationDocumentAction(
  _state: InvestigationActionState,
  form: FormData,
): Promise<InvestigationActionState> {
  const taskId = text(form, "task_id");
  const deliveryHash = text(form, "delivery_hash");
  const materialId = text(form, "material_id");
  const reason = text(form, "reason");
  if (!UUID.test(taskId) || !SHA256.test(deliveryHash) || !materialId || materialId.length > 512) {
    return invalid("当前任务、材料版本或材料标识不可操作，请刷新详情。");
  }
  // The backend requires 8–2000 characters; validating the same lower bound here
  // turns a 7-character reason into a local hint instead of a server conflict.
  if (reason.length < 8 || reason.length > 2000) return invalid("请填写 8–2000 个字符的排除理由，说明为何不解析此材料。");
  return submit(`/investigations/${taskId}/document-exclusions`, {
    delivery_hash: deliveryHash, material_id: materialId, reason,
  }, text(form, "request_key"),
    "已记录排除：此材料改用无文本证据块的解析器，不计入已核对，其字段不得作为块级依据，仅保留原件整文件引用。");
}

/**
 * Undoes {@link excludeInvestigationDocumentAction}. The material returns to be
 * parsed, so every derived document and field stays unverified until the
 * operator re-runs document preparation.
 */
export async function revokeInvestigationDocumentAction(
  _state: InvestigationActionState,
  form: FormData,
): Promise<InvestigationActionState> {
  const taskId = text(form, "task_id");
  const deliveryHash = text(form, "delivery_hash");
  const materialId = text(form, "material_id");
  const reason = text(form, "reason");
  if (!UUID.test(taskId) || !SHA256.test(deliveryHash) || !materialId || materialId.length > 512) {
    return invalid("当前任务、材料版本或材料标识不可操作，请刷新详情。");
  }
  if (reason.length < 8 || reason.length > 2000) return invalid("请填写 8–2000 个字符的撤销依据，说明为何恢复解析此材料。");
  return submit(`/investigations/${taskId}/document-exclusions/revoke`, {
    delivery_hash: deliveryHash, material_id: materialId, reason,
  }, text(form, "request_key"),
    "已撤销排除：该材料恢复为待解析，需重新准备文档证据后再核对；撤销同样不等于已核对。");
}

export async function bindInvestigationAction(
  _state: InvestigationActionState, form: FormData,
): Promise<InvestigationActionState> {
  const taskId = text(form, "task_id");
  const deliveryHash = text(form, "delivery_hash");
  const [opportunityId, rawVersion, extra] = text(form, "target").split("/");
  const previous = text(form, "previous_binding_id");
  const reason = text(form, "reason");
  const version = Number(rawVersion);
  if (!UUID.test(taskId) || !SHA256.test(deliveryHash) || !UUID.test(opportunityId ?? "")
    || !Number.isSafeInteger(version) || version < 1 || extra !== undefined
    || (previous && !UUID.test(previous))) return invalid("请选择明确的机会版本；材料或关联版本变化时请刷新详情。");
  if (!reason || reason.length > 2000) return invalid("请填写 1–2000 个字符，说明确认归属的依据。");
  const positions: { entity_id: string; opportunity_unit_id: string; opportunity_unit_version_id: string }[] = [];
  for (const [key, value] of form.entries()) {
    if (!key.startsWith("position:") || !value) continue;
    const [unitId, unitVersion, extraUnit] = String(value).split("/");
    const entityId = key.slice("position:".length);
    if (!entityId || entityId.length > 256 || !UUID.test(unitId) || !UUID.test(unitVersion)
      || extraUnit !== undefined) return invalid("岗位版本无效，请刷新后重新选择。");
    positions.push({ entity_id: entityId, opportunity_unit_id: unitId, opportunity_unit_version_id: unitVersion });
  }
  if (new Set(positions.map(p => p.entity_id)).size !== positions.length
    || new Set(positions.map(p => p.opportunity_unit_id)).size !== positions.length) return invalid("同一岗位不能重复关联，请核对每一项。");
  return submit(`/investigations/${taskId}/bindings`, {
    delivery_hash: deliveryHash, opportunity_id: opportunityId, opportunity_version: version,
    positions, previous_binding_id: previous || null, reason,
  }, text(form, "request_key"), "归属确认已记录，材料来源已冻结；尚未关联的岗位和所有字段事实仍待处理。");
}

export async function registerInvestigationIdentityAction(
  _state: InvestigationActionState, form: FormData,
): Promise<InvestigationActionState> {
  const taskId = text(form, "task_id"), deliveryHash = text(form, "delivery_hash");
  const previous = text(form, "previous_binding_id"), reason = text(form, "reason");
  if (!UUID.test(taskId) || !SHA256.test(deliveryHash) || (previous && !UUID.test(previous))) return invalid("任务、材料或归属版本无效，请刷新详情。");
  if (!reason || reason.length > 2000) return invalid("请填写登记核对依据（1–2000 个字符）。");
  const positions = form.getAll("new_position").map(value => {
    const entityId = String(value);
    return { entity_id: entityId, unit_key: text(form, `unit_key:${entityId}`), label: text(form, `label:${entityId}`) };
  });
  if ((previous && !positions.length) || positions.length > 2000
    || positions.some(p => !p.entity_id || p.entity_id.length > 256 || !p.unit_key || p.unit_key.length > 256 || !p.label || p.label.length > 500)
    || new Set(positions.map(p => p.entity_id)).size !== positions.length
    || new Set(positions.map(p => p.unit_key.replace(/\s+/g, " ").toLowerCase())).size !== positions.length) return invalid("请勾选要登记的岗位，填写不重复的识别键及岗位名称。");
  if (previous) return submit(`/investigations/${taskId}/positions`, {
    delivery_hash: deliveryHash, previous_binding_id: previous, positions, reason,
  }, text(form, "request_key"), "岗位身份已登记，已有归属保留；字段内容仍待核验。");
  const title = text(form, "canonical_title"), type = text(form, "type"), issuer = text(form, "issuer_name");
  const allowedTypes = ["PUBLIC_INSTITUTION_JOB", "STATE_OWNED_ENTERPRISE_JOB", "CIVIL_SERVICE", "GRASSROOTS_PROGRAM", "YOUTH_POLICY_BENEFIT", "COMPETITION", "RESEARCH_PROGRAM", "SCHOLARSHIP", "YOUTH_DEVELOPMENT_PROGRAM"];
  if (!title || title.length > 500 || !issuer || issuer.length > 500 || !allowedTypes.includes(type)) return invalid("请依据公告填写名称、发布单位，并明确选择机会类别。");
  return submit(`/investigations/${taskId}/identity`, { delivery_hash: deliveryHash,
    canonical_title: title, type, issuer_name: issuer, positions, reason,
  }, text(form, "request_key"), "内部机会身份已登记并关联材料，内容保持待核验，尚未公开发布。");
}

export async function investigationRuleAction(
  _state: InvestigationActionState, form: FormData,
): Promise<InvestigationActionState> {
  const taskId = text(form, "task_id"), deliveryHash = text(form, "delivery_hash");
  const bindingId = text(form, "binding_id"), checkId = text(form, "check_id");
  const factPreparationId = text(form, "fact_preparation_id"), factSetId = text(form, "fact_set_id"), entityId = text(form, "entity_id");
  if (![taskId, bindingId, checkId, factPreparationId, factSetId].every(value => UUID.test(value))
    || !SHA256.test(deliveryHash) || !entityId || entityId.length > 256) return invalid("请选择当前已保存的审核事实集及核验回执。");
  const body = { delivery_hash: deliveryHash, binding_id: bindingId, check_id: checkId,
    fact_preparation_id: factPreparationId, fact_set_id: factSetId, entity_id: entityId };
  const kind = text(form, "kind");
  if (kind === "prepare") return submit(`/investigations/${taskId}/rules`, body, text(form, "request_key"), "规则候选已整理，未知和不支持的条件继续保留；规则尚未批准。");
  const preparationId = text(form, "rule_preparation_id"), candidateId = text(form, "rule_candidate_id");
  const decision = text(form, "decision"), reason = text(form, "reason");
  if (kind !== "decision" || !UUID.test(preparationId) || !UUID.test(candidateId)
    || !Object.hasOwn(ruleDecisions, decision) || !reason || reason.length > 2000) return invalid("请明确选择规则决定，并填写 1–2000 个字符的核对依据。");
  const ids = form.getAll("evidence_ref_id").map(String);
  if (!ids.length || ids.length > 2000 || new Set(ids).size !== ids.length || ids.some(id => !UUID.test(id))) return invalid("规则证据清单无效，请刷新详情。");
  const evidence = ids.map(id => ({ evidence_ref_id: id, authority: text(form, `authority:${id}`) || null,
    relation: text(form, `relation:${id}`) || null, effective_at: text(form, `effective_at:${id}`) || null,
    applicability: text(form, `applicability:${id}`), reason: text(form, `evidence_reason:${id}`) }));
  if (evidence.some(e => (e.authority !== null && !Object.hasOwn(ruleAuthorities, e.authority))
    || (e.relation !== null && !Object.hasOwn(ruleRelations, e.relation)) || !Object.hasOwn(ruleApplicability, e.applicability)
    || !e.reason || e.reason.length > 2000 || (e.effective_at !== null && !isExplicitRuleTime(e.effective_at)))) return invalid("请为每条证据填写核对依据；时间如已确认，须填写真实日期、时间及时区，不能只填日期。");
  if (decision === "APPROVE" && evidence.some(e => !e.authority || !e.relation || !e.effective_at
    || e.applicability !== "APPLIES_TO_EXACT_TARGET")) return invalid("批准需要逐条明确证据的权威级别、支持关系、生效时间及精确适用目标；未解决事项可保留待裁决。");
  return submit(`/investigations/${taskId}/rules/decisions`, { ...body, rule_preparation_id: preparationId,
    rule_candidate_id: candidateId, decision, evidence, reason }, text(form, "request_key"), "独立规则审核已记录；完整条件覆盖与资格判断尚待后续处理。");
}

export async function investigationFactAction(
  _state: InvestigationActionState, form: FormData,
): Promise<InvestigationActionState> {
  const taskId = text(form, "task_id"), deliveryHash = text(form, "delivery_hash"), bindingId = text(form, "binding_id");
  if (!UUID.test(taskId) || !SHA256.test(deliveryHash) || !UUID.test(bindingId)) return invalid("材料或归属版本无效，请刷新详情。");
  const checkId = text(form, "check_id");
  if (!UUID.test(checkId)) return invalid("请先准备当前版本的文档核验回执。");
  const body = { delivery_hash: deliveryHash, binding_id: bindingId, check_id: checkId };
  const kind = text(form, "kind");
  if (kind === "prepare") return submit(`/investigations/${taskId}/facts`, body, text(form, "request_key"), "候选字段已整理，请检查未定位、未绑定及未知项；尚未批准事实。");
  const preparationId = text(form, "preparation_id"), reason = text(form, "reason");
  if (!UUID.test(preparationId) || !reason || reason.length > 2000) return invalid("请选择当前候选清单，并填写 1–2000 个字符的审核依据。");
  if (kind === "decision") {
    const candidateId = text(form, "candidate_id"), decision = text(form, "decision");
    const support = text(form, "evidence_support"), precedence = text(form, "precedence_check");
    if (!UUID.test(candidateId) || !["APPROVE", "REJECT", "UNKNOWN", "NEEDS_ADJUDICATION"].includes(decision)
      || !["SUPPORTED", "UNSUPPORTED", "UNKNOWN"].includes(support) || !["PASSED", "FAILED", "UNKNOWN"].includes(precedence)) return invalid("请逐项选择字段决定、原文支持情况及更正／例外核查结果。");
    if (decision === "APPROVE" && (support !== "SUPPORTED" || precedence !== "PASSED")) return invalid("批准需要原文明确支持，并完成更正、适用范围及例外核查。");
    return submit(`/investigations/${taskId}/facts/decisions`, { ...body, preparation_id: preparationId,
      candidate_id: candidateId, decision, evidence_support: support, precedence_check: precedence, reason,
    }, text(form, "request_key"), "独立字段审核已记录；资格结论及公开发布仍需后续处理。");
  }
  const entityId = text(form, "entity_id");
  if (kind !== "promote" || !entityId || entityId.length > 256) return invalid("请选择明确的公告或岗位目标。");
  const supersedes = text(form, "supersedes_id");
  if (supersedes && !UUID.test(supersedes)) return invalid("被替代事实集的标识无效，请核对当前版本。");
  return submit(`/investigations/${taskId}/facts/promotions`, { ...body, preparation_id: preparationId,
    entity_id: entityId, supersedes_id: supersedes || null, reason,
  }, text(form, "request_key"), "该目标的审核事实集已保存；未知及未接入条件继续保留，尚未形成完整资格结论。");
}

/**
 * Records an explicit operator intent to run a queued investigation. Reuses the
 * shared {@link submit} idempotency key and 401/403/409 classification, so a
 * lost receipt can be replayed without writing a second intent. This action
 * never runs automatically — it only fires when the operator clicks "发起调查".
 */
export async function requestInvestigationDispatchAction(
  _state: InvestigationActionState,
  form: FormData,
): Promise<InvestigationActionState> {
  const taskId = text(form, "task_id");
  if (!UUID.test(taskId)) return invalid("当前任务标识无效，请刷新详情后重试。");
  return submit(investigationDispatchPath(taskId), {}, text(form, "request_key"),
    text(form, "kind") === "recover"
      ? "材料回收请求已记录；本次只下载已有远端材料，不会重新发出调查请求。"
      : "已发起调查。处理进程会在就绪后安排执行；发起失败会在任务上标记原因，不会自动重试多次。",
    investigationLoginHelp);
}
