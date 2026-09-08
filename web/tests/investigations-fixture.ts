import type { InvestigationTask, InvestigationBindingTarget, InvestigationEvidenceCheck } from "../lib/investigations";

export const bindingTarget: InvestigationBindingTarget = {
  opportunity_id: "019d0000-0000-7000-8000-000000000911", public_id: "opp_019d0000000070008000000000000911",
  version: 1, title: "示例正式机会（合成数据）", positions: [{
    unit_id: "019d0000-0000-7000-8000-000000000912", version_id: "019d0000-0000-7000-8000-000000000913",
    public_id: "unit_019d0000000070008000000000000912", key: "P001", label: "示例教学岗位",
  }],
};

export const preparedDocuments: NonNullable<InvestigationTask["document_preparation"]> = {
  scope: "DOCUMENT_EVIDENCE_ONLY", status: "PREPARED", material_count: 1, prepared_count: 1,
  materials: [{ material_id: "attachment-1", outcome: "SUCCEEDED", error_code: null,
    document_id: "019d0000-0000-7000-8000-000000000904", document_parse_key: "d".repeat(64),
    parser_name: "deepaha-evidence-reader", parser_version: "a".repeat(64), parse_contract_version: "reader-document-block-contract-v1",
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
  binding_entities: [{ id: "position-1", name: "教学岗位", kind: "position", code: "P001" }],
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

export const evidenceCheck: InvestigationEvidenceCheck = {
  check_id: "019d0000-0000-7000-8000-000000000920", input_hash: "a".repeat(64),
  result_hash: "d".repeat(64), delivery_hash: task.delivery_hash!, created_at: task.updated_at,
  scope: "MECHANICAL_EVIDENCE_ONLY", verdict: "PASS", counts: { PASS: 1, FAIL: 0, UNVERIFIED: 0 },
  references: [{ fact_index: 0, reference_index: 0, entity_id: "position-1", field: "education",
    artifact_id: "attachment-1", verdict: "PASS", binding_reason: null,
    verification: {
      artifact_id: "attachment-1", artifact_sha256: "c".repeat(64), quote: task.facts[0].evidence[0].quote,
      original_locator: task.facts[0].evidence[0].locator,
      reader: { name: "xlsx_literal", version: "synthetic-test/1", parse_contract: "synthetic/1", comparison_version: "literal/1" },
      representation_sha256: "e".repeat(64), content_support: "FOUND", declared_locator: "VERIFIED",
      binding: "BOUND", precision: "SPAN", verdict: "PASS", reason_codes: [], verifier_version: "evidence-literal/1",
      matches: [{ projection_id: "sheet/岗位表/D5", source_spans: [{ origin_id: "岗位表!D5", start: 0, end: 10 }] }],
    },
    persistent_binding: { document_id: "019d0000-0000-7000-8000-000000000904", document_parse_key: "d".repeat(64),
      parse_attempt_id: "019d0000-0000-7000-8000-000000000905", block_id: "019d0000-0000-7000-8000-000000000906",
      evidence_ref_id: "019d0000-0000-7000-8000-000000000907", evidence_binding_hash: "f".repeat(64) },
  }],
};
