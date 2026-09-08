import type { InvestigationTask, InvestigationBindingTarget, InvestigationEvidenceCheck, InvestigationFactPreparation, InvestigationRulePreparation } from "../lib/investigations";

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
  facts: [{ entity_id: "position-1", field: "学历要求", value: "硕士及以上", status: "CONFIRMED",
    note: "示例疑点：应届毕业生的证书取得时间仍需核对。",
    evidence: [{ artifact_id: "attachment-1", quote: "学历要求：硕士及以上", locator: { sheet: "岗位表", row: 5, column: "D" }, sha256: "c".repeat(64), mechanically_verified: true }],
  }],
  materials: [{ artifact_id: "attachment-1", url: `${source.url}/jobs.xlsx`, sha256: "c".repeat(64), media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", size_bytes: 1024 }],
};

export const evidenceCheck: InvestigationEvidenceCheck = {
  check_id: "019d0000-0000-7000-8000-000000000920", input_hash: "a".repeat(64),
  result_hash: "d".repeat(64), delivery_hash: task.delivery_hash!, created_at: task.updated_at,
  scope: "MECHANICAL_EVIDENCE_ONLY", verdict: "PASS", counts: { PASS: 1, FAIL: 0, UNVERIFIED: 0 },
  references: [{ fact_index: 0, reference_index: 0, entity_id: "position-1", field: "学历要求",
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

export const factPreparation: InvestigationFactPreparation = {
  preparation_id: "019d0000-0000-7000-8000-000000000930", binding_id: "019d0000-0000-7000-8000-000000000921",
  check_id: evidenceCheck.check_id, mapping_version: "direct-wma-field-mapping/2.0.0", result_hash: "a".repeat(64),
  targets: [{ entity_id: "position-1", name: "教学岗位", target_scope: "UNIT", opportunity_id: bindingTarget.opportunity_id,
    opportunity_version: 1, opportunity_unit_id: bindingTarget.positions[0].unit_id,
    opportunity_unit_version_id: bindingTarget.positions[0].version_id, extraction_run_id: "019d0000-0000-7000-8000-000000000931" }],
  rows: [{ source_index: 0, entity_id: "position-1", original: task.facts[0], original_field: "学历要求",
    field_name: "education_requirements", raw_value: "硕士及以上", normalized_value_candidate: { minimum_level: "MASTER" },
    abstained: false, candidate_id: "019d0000-0000-7000-8000-000000000932", issue_codes: [],
    evidence: [{ reference: task.facts[0].evidence[0], check_reference: evidenceCheck.references[0],
      binding: { block_id: evidenceCheck.references[0].persistent_binding!.block_id,
        evidence_ref_id: evidenceCheck.references[0].persistent_binding!.evidence_ref_id,
        block_text: "学历要求：硕士及以上", structural_locator: { kind: "reader_anchor", projection_id: "sheet/岗位表/D5" } } }],
  }], decisions: {}, promotions: {}, active_fact_sets: {},
};

export const rulePreparation: InvestigationRulePreparation = {
  rule_preparation_id: "019d0000-0000-7000-8000-000000000940", fact_preparation_id: factPreparation.preparation_id,
  fact_set_id: "019d0000-0000-7000-8000-000000000933", entity_id: "position-1",
  binding_id: factPreparation.binding_id, delivery_hash: task.delivery_hash!, check_id: evidenceCheck.check_id,
  compiler_version: "direct-wma-rule-bridge/2.0.0+deriver-1.0.1", result_hash: "f".repeat(64),
  fact_preparation_hash: factPreparation.result_hash, fact_set_version: 1,
  source_bundle_revision_id: "019d0000-0000-7000-8000-000000000915", scope_status: "COMPLETE_CONDITION_REVIEW_REQUIRED",
  target: factPreparation.targets[0], source_rows: factPreparation.rows,
  rows: [{ verified_fact_id: "019d0000-0000-7000-8000-000000000941", candidate_id: factPreparation.rows[0].candidate_id!,
    field_name: "education_requirements", fact_state: "KNOWN", normalized_value: { minimum_level: "MASTER" },
    rule_candidate_id: "019d0000-0000-7000-8000-000000000942", reason_code: "INDEPENDENT_RULE_REVIEW_REQUIRED",
    payload: { field: "education_level", operator: "GTE", value_type: "STRING", value: "MASTER", code: "synthetic-rule" },
    evidence_ref_ids: [evidenceCheck.references[0].persistent_binding!.evidence_ref_id],
    evidence: [{ evidence_ref_id: evidenceCheck.references[0].persistent_binding!.evidence_ref_id,
      document_id: evidenceCheck.references[0].persistent_binding!.document_id, block_id: evidenceCheck.references[0].persistent_binding!.block_id,
      text: factPreparation.rows[0].evidence[0].binding!.block_text,
      structural_locator: factPreparation.rows[0].evidence[0].binding!.structural_locator }],
  }], decisions: {}, decision_history: [],
};

export function ruleReadyTask(): InvestigationTask {
  const facts = structuredClone(factPreparation);
  facts.promotions[rulePreparation.entity_id] = { fact_set_id: rulePreparation.fact_set_id, status: "ACTIVE", reason: "Synthetic" };
  facts.active_fact_sets[rulePreparation.entity_id] = { fact_set_id: rulePreparation.fact_set_id, version: 1, source_bundle_revision_id: rulePreparation.source_bundle_revision_id };
  return { ...structuredClone(task), status: "APPROVED", evidence_check: structuredClone(evidenceCheck),
    fact_review: { current: facts, history: [] }, rule_review: { current: [structuredClone(rulePreparation)], history: [] },
    entity_binding: { binding_id: factPreparation.binding_id, sequence: 1, opportunity_id: bindingTarget.opportunity_id,
      opportunity_version: 1, opportunity_public_id: bindingTarget.public_id, opportunity_title: bindingTarget.title,
      source_bundle_revision_id: rulePreparation.source_bundle_revision_id, canonical_bundle_hash: "a".repeat(64), bundle_status: "FROZEN",
      positions: [], unmapped_position_ids: [], reason: "Synthetic", created_at: task.updated_at },
  };
}

export function unitSnapshotFixture(): { task: InvestigationTask; snapshot: import("../lib/unit-snapshots").InvestigationUnitSnapshot } {
  const current = ruleReadyTask(), prep = current.rule_review!.current[0];
  const candidate = prep.rows[0].rule_candidate_id!, decisionId = "019d0000-0000-7000-8000-000000000980";
  prep.decisions[candidate] = { decision_id: decisionId, rule_candidate_id: candidate, decision: "APPROVE", reason: "合成独立批准，仅测试流程", evidence: [], reviewer_id: "synthetic-browser-reviewer", created_at: task.updated_at };
  prep.decision_history.push(prep.decisions[candidate]);
  for (const [index, field] of ["户籍", "专业", "证书", "其他岗位条件"].entries()) {
    const source = structuredClone(prep.source_rows[0]);
    source.source_index = index + 1; source.original_field = field; source.field_name = field;
    source.candidate_id = null; source.original = { ...source.original, field, value: "合成待核对条件", note: null };
    if (index === 0) { source.original.status = "UNKNOWN"; source.original.value = null; }
    if (index === 1) { source.evidence[0].binding = null; source.evidence[0].check_reference = { ...source.evidence[0].check_reference!, verdict: "UNVERIFIED", persistent_binding: null }; }
    if (index === 3) { source.entity_id = "peer"; source.original.entity_id = "peer"; }
    prep.source_rows.push(source);
  }
  const states = ["KNOWN", "UNKNOWN", "UNLOCATED", "REJECTED"];
  return { task: current, snapshot: {
    plan_id: "019d0000-0000-7000-8000-000000000981", plan_hash: "a".repeat(64), context_hash: "b".repeat(64), reviewer_id: "synthetic-browser-reviewer", created_at: task.updated_at,
    plan: {
      qualification_plan_id: "019d0000-0000-7000-8000-000000000981", contract_version: "unit-qualification/2.0.0",
      target: { opportunity_id: bindingTarget.opportunity_id, opportunity_version: 1, unit_id: bindingTarget.positions[0].unit_id, unit_version: 1, unit_version_id: bindingTarget.positions[0].version_id },
      manifest: { preparation_id: prep.fact_preparation_id, preparation_sha256: prep.fact_preparation_hash,
        upstream_blockers: ["SOURCE_COMPLETENESS_UNVERIFIED", "SOURCE_NOTES_UNREVIEWED"],
        conditions: prep.source_rows.slice(0, 4).map((source, index) => ({ condition_id: `source:${index}`, source_entity_id: source.entity_id, source_index: index, field_name: source.field_name!, scope: "UNIT", state: states[index], source_sha256: "c".repeat(64), fact_id: index === 0 ? prep.rows[0].verified_fact_id : null, evidence_ref_ids: index === 0 ? prep.rows[0].evidence_ref_ids : [] })),
      },
      dispositions: states.map((_, index) => ({ condition_id: `source:${index}`, kind: index === 0 ? "RULE" : "UNRESOLVED", rule_ids: index === 0 ? [candidate] : [], decision_id: index === 0 ? decisionId : null, reason: "Synthetic" })),
      rules: [{ rule_id: candidate, field: "education_level", operator: "GTE", value: "MASTER" }],
      admissions: [{ rule_id: candidate, approval_decision_id: decisionId, producer_principal_id: "component:synthetic", reviewer_principal_id: "human:synthetic-reviewer", reviewed_at: task.updated_at,
        evidence_validity: [{ evidence_ref_id: prep.rows[0].evidence_ref_ids[0], valid_from: task.updated_at, valid_until: null }] }],
    },
    context: { adapter_version: "investigation-unit-snapshot/1.0.0", rule_preparation_id: prep.rule_preparation_id, rule_preparation_hash: prep.result_hash,
      fact_preparation_hash: prep.fact_preparation_hash, binding_id: prep.binding_id, check_id: prep.check_id, delivery_hash: prep.delivery_hash,
      fact_set_id: prep.fact_set_id, fact_set_version: 1, source_bundle_revision_id: prep.source_bundle_revision_id,
      source_row_count: 5, excluded_source_rows: [{ source_index: 4, entity_id: "peer", source_sha256: "c".repeat(64), reason: "DIFFERENT_ENTITY_SCOPE" }],
      source_notes: [{ condition_id: "source:0", note: task.facts[0].note! }],
      evidence_reference_counts: { PASS: 4, FAIL: 0, UNVERIFIED: 1 }, unresolved_source_references: [prep.source_rows[2].evidence[0].check_reference!],
    },
  } };
}
