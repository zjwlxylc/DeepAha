const statuses: Record<string, string> = {
  QUEUED: "已登记，等待执行", CREATING: "正在建立调查", PREPARING: "正在准备调查材料",
  INVESTIGATING: "正在调查", COLLECTING: "正在回收材料", PENDING_REVIEW: "材料已回收，待人工审核",
  APPROVED: "内部材料已批准", REJECTED: "内部材料已退回", FAILED_PREPARATION: "调查准备失败",
  EXECUTION_UNCERTAIN: "执行结果尚不确定", COLLECTION_RETRYABLE: "材料回收未完成",
  FAILED_VALIDATION: "材料核验未通过", EXPIRED: "任务已超时",
};

export function investigationStatus(status: string): string {
  return statuses[status] ?? "状态待核对";
}

const failures: Record<string, string> = {
  WMA_REMOTE_REFUSED: "调查服务拒绝了本次执行，尚不能确认交付完整。",
  WMA_OUTPUT_LIMIT_REACHED: "调查达到输出长度上限，交付内容可能不完整。",
  WMA_REQUEST_LIMIT_REACHED: "调查达到单轮请求上限，仍可能有材料未处理。",
  WMA_REMOTE_CANCELLED: "调查服务已取消本次执行，已有材料仍需回收与核验。",
  WMA_NON_SUCCESS_STOP: "调查没有正常结束，尚不能确认交付完整。",
};

export function investigationFailureMessage(code: string): string {
  return failures[code] ?? "本次任务未完成，请先核对运行记录和已有材料。";
}

export function investigationIssueMessage(issue: string): string {
  const code = issue.split(":")[0];
  if (code === "EVIDENCE_FORMAT_REVIEW_REQUIRED") return "这种文件格式还不能自动核对，请下载原件检查。";
  if (code === "EVIDENCE_LOCATOR_REVIEW_REQUIRED") return "引用的位置还需核对，请对照原文确认对应内容。";
  if (code === "EVIDENCE_CONTENT_REVIEW_REQUIRED") return "系统尚不能确认引用内容，请查看原件。";
  return /^[A-Z][A-Z_0-9]+(?::|$)/.test(issue) ? "有一项检查需要进一步处理，具体记录可在下方展开查看。" : issue;
}
