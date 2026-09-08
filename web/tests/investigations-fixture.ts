import type { InvestigationTask } from "../lib/investigations";

export const preparedDocuments: NonNullable<InvestigationTask["document_preparation"]> = {
  scope: "DOCUMENT_EVIDENCE_ONLY", status: "PREPARED", material_count: 1, prepared_count: 1,
  materials: [{ material_id: "attachment-1", outcome: "SUCCEEDED", error_code: null,
    document_id: "019d0000-0000-7000-8000-000000000904", document_parse_key: "d".repeat(64),
    parser_name: "xlsx_openpyxl", parser_version: "0.8.0", parse_contract_version: "p9b-document-block-contract-v0.8.0",
    block_count: 8, evidence_ref_count: 9 }],
};

export const taskId = "019d0000-0000-7000-8000-000000000901";
export const source = {
  source_id: "019d0000-0000-7000-8000-000000000902",
  endpoint_id: "019d0000-0000-7000-8000-000000000903",
  authority_name: "示例主管部门",
  url: "https://official.example.gov.cn/notices",
  allowed_hosts: ["official.example.gov.cn"],
};
export const task: InvestigationTask = {
  task_id: taskId, status: "PENDING_REVIEW", notice_url: `${source.url}/1`,
  source_id: source.source_id, endpoint_id: source.endpoint_id,
  brief: "检查示例公告与全部岗位条件", calibration: true,
  created_at: "2026-09-07T08:00:00Z", updated_at: "2026-09-07T09:00:00Z",
  error_code: null, contract_hash: "a".repeat(64), delivery_hash: "b".repeat(64),
  issues: [], review: null,
  opportunities: {
    opportunity_name: "示例招聘公告", publish_unit: "示例主管部门",
    units: [{ id: "unit-1", name: "示例学院", positions: [{ id: "position-1", name: "教学岗位", code: "P001" }] }],
  },
  facts: [{ entity_id: "position-1", field: "education", value: "硕士及以上", status: "CONFIRMED",
    note: "示例疑点：应届毕业生的证书取得时间仍需核对。",
    evidence: [{ artifact_id: "attachment-1", quote: "学历要求：硕士及以上", locator: { sheet: "岗位表", row: 5, column: "D" }, sha256: "c".repeat(64), mechanically_verified: true }],
  }],
  materials: [{ artifact_id: "attachment-1", url: `${source.url}/jobs.xlsx`, sha256: "c".repeat(64), media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", size_bytes: 1024 }],
};
