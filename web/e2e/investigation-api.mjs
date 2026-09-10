// Browser fixtures only. This process never calls an official source or WMA.
import { createServer } from "node:http";
import { source, task, preparedDocuments, bindingTarget, evidenceCheck, factPreparation, rulePreparation, ruleReadyTask, unitSnapshotFixture } from "../tests/investigations-fixture.ts";
import { applicabilityViewFixture, applicabilityDecisionFixture, applicabilityIds } from "../tests/rule-applicability-fixture.ts";
import { announcementSnapshotFixture, announcementRecordFixture } from "../tests/announcement-snapshot-fixture.ts";
import { handleGroup, resetGroups, seedGroup } from "./group-source-api.mjs";
import { handleGroupFacts, resetGroupFacts, seedGroupFacts } from "./group-fact-api.mjs";

let current = structuredClone(task);
let dropNextReceipt = false;
const receipts = new Map();
let posts = 0;
let unitSnapshot = null;
let staleSnapshot = false;
let applicability = null;
let applicabilityMode = null;
let announcement = null;
let announcementMode = null;
const announcementRecords = new Map();
function announcementFailure(response) {
  const status = { stale: 409, forbidden: 403, unavailable: 503 }[announcementMode];
  if (!status) return false;
  response.writeHead(status); response.end(JSON.stringify({ detail: "synthetic private failure must not leak" })); return true;
}
function applicabilityOptions() {
  const first = applicability.view.evidence_options[0];
  return [first, { ...first, member_id: applicabilityIds.secondBlock, material_id: "attachment-second", source_url: "https://example.test/notices/copied-announcement.html" }];
}
const server = createServer(async (request, response) => {
  const url = new URL(request.url, "http://127.0.0.1:3097"), path = url.pathname;
  response.setHeader("Content-Type", "application/json");
  response.setHeader("Cache-Control", "private, no-store");
  if (path === "/reset") { resetGroups(); resetGroupFacts(); }
  if (path === "/seed-group-facts") { const data = seedGroupFacts(url.searchParams.has("legacy")); current = data.source.task; response.end(JSON.stringify({ task_id: current.task_id, group_id: data.source.preview.registration.group_binding_id })); return; }
  if (await handleGroupFacts(request, response, url)) return;
  if (path === "/seed-group-source") { current = seedGroup(); response.end(JSON.stringify({ task_id: current.task_id, entity_id: "unit-1" })); return; }
  if (await handleGroup(request, response, url)) return;
  if (path === "/reset") { current = structuredClone(task); receipts.clear(); posts = 0; dropNextReceipt = false; unitSnapshot = null; staleSnapshot = false; applicability = null; applicabilityMode = null; announcement = null; announcementMode = null; announcementRecords.clear(); response.end("{}"); return; }
  if (path === "/seed-announcement-snapshot") {
    announcement = announcementSnapshotFixture(unitSnapshotFixture()); current = announcement.task; unitSnapshot = announcement.input.snapshot.base_v2;
    response.end(JSON.stringify({ task_id: current.task_id, base_plan_id: unitSnapshot.plan_id })); return;
  }
  if (path === "/announcement-snapshot-mode") {
    announcementMode = url.searchParams.get("kind");
    if (announcementMode === "changed" && announcement) {
      const row = announcement.input.snapshot.announcement_conditions[0], app = row.applicability;
      const previous = app.decision_id;
      app.decision_id = "019d0000-0000-7000-8000-000000002900"; app.sequence = 2;
      app.request = { ...app.request, previous_decision_id: previous, reason: "合成工程更正：最新决定明确排除", outcome: "DOES_NOT_APPLY" };
      row.disposition = "EXCLUDED"; announcement.input.dependencies_hash = "e".repeat(64);
    }
    response.end("{}"); return;
  }
  if (path === "/seed-rule-applicability") { applicability = applicabilityViewFixture(unitSnapshotFixture()); current = applicability.task; unitSnapshot = applicability.snapshot; response.end(JSON.stringify(applicability.identity)); return; }
  if (path === "/rule-applicability-mode") { applicabilityMode = url.searchParams.get("kind"); response.end("{}"); return; }
  if (path === "/applicability-records") { response.end(JSON.stringify(applicability?.view.history ?? [])); return; }
  if (path === "/seed-unit-snapshot") { current = unitSnapshotFixture().task; response.end("{}"); return; }
  if (path === "/stale-unit-snapshot") { staleSnapshot = true; response.end("{}"); return; }
  if (path === "/seed-rule-review") { current = ruleReadyTask(); current.rule_review = { current: [], history: [] }; response.end("{}"); return; }
  if (path === "/drop-next-receipt") { dropNextReceipt = true; response.end("{}"); return; }
  if (path === "/receipts") { response.end(JSON.stringify({ mutations: receipts.size, posts })); return; }
  if (request.headers.authorization !== "Bearer synthetic-browser-reviewer") {
    response.writeHead(401); response.end("{}"); return;
  }
  if (path.endsWith("/sources")) { response.end(JSON.stringify({ sources: [source] })); return; }
  if (path.endsWith("/binding-targets")) { response.end(JSON.stringify({ targets: [bindingTarget] })); return; }
  if (request.method === "GET" && path.endsWith("/announcement-snapshot-input")) {
    if (announcementFailure(response)) return;
    if (!announcement || path !== `/api/v1/local-human-test/investigations/${current.task_id}/unit-plans/${unitSnapshot.plan_id}/announcement-snapshot-input`) { response.writeHead(404); response.end("{}"); return; }
    response.end(JSON.stringify(announcement.input)); return;
  }
  if (request.method === "GET" && path.includes("/announcement-snapshots/")) {
    if (announcementFailure(response)) return;
    const record = announcementRecords.get(path.split("/").at(-1));
    if (!record || !path.startsWith(`/api/v1/local-human-test/investigations/${current.task_id}/announcement-snapshots/`)) { response.writeHead(404); response.end("{}"); return; }
    if (record.dependencies_hash !== announcement.input.dependencies_hash) { response.writeHead(409); response.end("{}"); return; }
    response.end(JSON.stringify(record)); return;
  }
  if (request.method === "GET" && path.includes("/rule-applicability/")) {
    const id = applicability?.identity;
    if (!id || path !== `/api/v1/local-human-test/investigations/${id.task_id}/unit-plans/${id.target_plan_id}/rule-applicability/${id.source_rule_preparation_id}/${id.source_rule_candidate_id}`) { response.writeHead(404); response.end("{}"); return; }
    if (["stale", "forbidden", "unavailable"].includes(applicabilityMode)) { response.writeHead({ stale: 409, forbidden: 403, unavailable: 503 }[applicabilityMode]); response.end(JSON.stringify({ detail: "synthetic private failure must not leak" })); return; }
    const after = url.searchParams.get("after"), view = applicability.view;
    if (after && after !== view.next_cursor) { response.writeHead(422); response.end("{}"); return; }
    const options = applicabilityMode === "empty" ? [] : applicabilityOptions();
    response.end(JSON.stringify({ ...view, context_hash: applicabilityMode === "changed" ? "f".repeat(64) : view.context_hash,
      evidence_options: after ? options.slice(1) : options.slice(0, 1), next_cursor: !after && options.length > 1 ? view.next_cursor : null })); return;
  }
  if (request.method === "GET" && path.includes("/unit-plans/")) {
    response.setHeader("Cache-Control", "private, no-store");
    if (staleSnapshot) { response.writeHead(409); response.end(JSON.stringify({ detail: { code: "RULE_FACT_SET_CONFLICT" } })); return; }
    if (!unitSnapshot || !path.endsWith(`/${unitSnapshot.plan_id}`)) { response.writeHead(404); response.end("{}"); return; }
    response.end(JSON.stringify(unitSnapshot)); return;
  }
  if (path.includes("/materials/")) {
    response.setHeader("Content-Type", "text/plain");
    response.setHeader("Content-Disposition", 'attachment; filename="original-cccccccccccccccc.xlsx"');
    response.end("synthetic browser fixture; not official material"); return;
  }
  if (request.method === "POST") {
    let body = "";
    for await (const chunk of request) body += chunk;
    posts += 1;
    const key = request.headers["idempotency-key"];
    if (path.endsWith("/announcement-snapshots")) {
      if (announcementFailure(response)) return;
      const values = JSON.parse(body);
      if (!announcement || path !== `/api/v1/local-human-test/investigations/${current.task_id}/unit-plans/${unitSnapshot.plan_id}/announcement-snapshots`
        || values.expected_dependencies_hash !== announcement.input.dependencies_hash || Object.keys(values).length !== 1) {
        response.writeHead(409); response.end("{}"); return;
      }
      // Match production's fresh dependency check before returning a cached receipt.
      let record = [...announcementRecords.values()].find(item => item.dependencies_hash === values.expected_dependencies_hash);
      if (!record) {
        record = announcementRecordFixture(announcement.input);
        record.snapshot_id = `019d0000-0000-7000-8000-${String(2001 + announcementRecords.size).padStart(12, "0")}`;
        record.snapshot_hash = announcementRecords.size ? "b".repeat(64) : "a".repeat(64);
        announcementRecords.set(record.snapshot_id, structuredClone(record));
        receipts.set(key, { path, body, task: structuredClone(record) });
      }
      if (dropNextReceipt) { dropNextReceipt = false; response.destroy(); return; }
      response.end(JSON.stringify(record)); return;
    }
    if (receipts.has(key)) {
      const receipt = receipts.get(key);
      if (receipt.body !== body || receipt.path !== path) { response.writeHead(409); response.end("{}"); return; }
      response.end(JSON.stringify(receipt.task)); return;
    }
    const values = JSON.parse(body);
    if (path.endsWith("/rule-applicability")) {
      const view = applicability?.view, id = applicability?.identity;
      if (applicabilityMode === "forbidden") { response.writeHead(403); response.end("{}"); return; }
      if (!view || ["stale", "changed"].includes(applicabilityMode) || values.context_hash !== view.context_hash
        || values.target_plan_id !== id.target_plan_id || values.source_rule_preparation_id !== id.source_rule_preparation_id
        || values.source_rule_candidate_id !== id.source_rule_candidate_id || values.previous_decision_id !== (view.latest?.decision_id ?? null)) {
        response.writeHead(409); response.end("{}"); return;
      }
      if (!["APPLIES", "DOES_NOT_APPLY", "NEEDS_ADJUDICATION"].includes(values.outcome) || !values.reason.trim()
        || values.reason.length > 2000 || values.evidence.length > 20 || (values.outcome !== "NEEDS_ADJUDICATION" && !values.evidence.length)
        || values.evidence.some(e => !e.quote.trim() || e.quote.length > 20000 || !applicabilityOptions().some(option => option.member_id === e.member_id && option.block_id === e.block_id && option.text.includes(e.quote)))) {
        response.writeHead(422); response.end("{}"); return;
      }
      const sequence = view.history.length + 1;
      const decision = { ...applicabilityDecisionFixture(view, values), sequence,
        decision_id: `019d0000-0000-7000-8000-${String(sequence + 1006).padStart(12, "0")}`,
        evidence_snapshot: values.evidence.map(e => {
          const original = applicabilityOptions().find(option => option.member_id === e.member_id && option.block_id === e.block_id);
          return { ...e, material_id: original.material_id, source_url: original.source_url, document_id: original.document_id, evidence_ref_id: original.evidence_ref_id, locator: original.locator, block_hash: "c".repeat(64), binding_hash: "d".repeat(64) };
        }),
      };
      view.latest = decision; view.history.push(decision);
      receipts.set(key, { path, body, task: structuredClone(decision) });
      if (dropNextReceipt) { dropNextReceipt = false; response.destroy(); return; }
      response.end(JSON.stringify(decision)); return;
    }
    if (path.endsWith("/unit-plans")) {
      unitSnapshot = unitSnapshotFixture().snapshot;
      receipts.set(key, { path, body, task: structuredClone(unitSnapshot) });
      if (dropNextReceipt) { dropNextReceipt = false; response.destroy(); return; }
      response.end(JSON.stringify(unitSnapshot)); return;
    }
    if (path.endsWith("/documents")) {
      if (values.delivery_hash !== current.delivery_hash) { response.writeHead(409); response.end("{}"); return; }
      current = { ...current, document_preparation: preparedDocuments, evidence_check: evidenceCheck, evidence_check_history: [evidenceCheck] };
    }
    else if (path.endsWith("/bindings")) {
      if (current.status !== "APPROVED" || current.document_preparation?.status !== "PREPARED"
        || values.delivery_hash !== current.delivery_hash) { response.writeHead(409); response.end("{}"); return; }
      current = { ...current, entity_binding: {
        ...values, binding_id: "019d0000-0000-7000-8000-000000000914", sequence: 1,
        source_bundle_revision_id: "019d0000-0000-7000-8000-000000000915", bundle_status: "FROZEN",
        canonical_bundle_hash: "f".repeat(64), opportunity_public_id: bindingTarget.public_id,
        opportunity_title: bindingTarget.title, created_at: task.updated_at,
        unmapped_position_ids: values.positions.length ? [] : ["position-1"],
      } };
    }
    else if (path.endsWith("/identity") || path.endsWith("/positions")) {
      const prior = current.entity_binding;
      const positions = [...(prior?.positions ?? []), ...values.positions.map(p => ({
        entity_id: p.entity_id, opportunity_unit_id: bindingTarget.positions[0].unit_id,
        opportunity_unit_version_id: bindingTarget.positions[0].version_id,
      }))];
      const sequence = (prior?.sequence ?? 0) + 1;
      current = { ...current, entity_binding: {
        ...values, positions, binding_id: `019d0000-0000-7000-8000-00000000092${sequence}`, sequence,
        opportunity_id: prior?.opportunity_id ?? bindingTarget.opportunity_id, opportunity_version: 1,
        source_bundle_revision_id: "019d0000-0000-7000-8000-000000000915", bundle_status: "FROZEN",
        canonical_bundle_hash: "f".repeat(64), opportunity_public_id: bindingTarget.public_id,
        opportunity_title: prior?.opportunity_title ?? values.canonical_title, created_at: task.updated_at,
        unmapped_position_ids: positions.length ? [] : ["position-1"],
      } };
    }
    else if (path.endsWith("/facts")) {
      current = { ...current, fact_review: { current: { ...structuredClone(factPreparation), binding_id: values.binding_id, check_id: values.check_id }, history: [] } };
    }
    else if (path.endsWith("/facts/decisions")) {
      current.fact_review.current.decisions[values.candidate_id] = {
        decision_id: `019d0000-0000-7000-8000-${String(receipts.size + 950).padStart(12, "0")}`,
        decision: values.decision, reason: values.reason, reviewer_id: "synthetic-browser-reviewer", created_at: task.updated_at,
      };
    }
    else if (path.endsWith("/facts/promotions")) {
      current.fact_review.current.promotions[values.entity_id] = {
        fact_set_id: "019d0000-0000-7000-8000-000000000933", status: "ACTIVE", reason: values.reason,
      };
      current.fact_review.current.active_fact_sets[values.entity_id] = { fact_set_id: "019d0000-0000-7000-8000-000000000933", version: 1, source_bundle_revision_id: rulePreparation.source_bundle_revision_id };
    }
    else if (path.endsWith("/rules")) {
      current.rule_review = { current: [{ ...structuredClone(rulePreparation), binding_id: values.binding_id, check_id: values.check_id }], history: [] };
    }
    else if (path.endsWith("/rules/decisions")) {
      const prep = current.rule_review.current[0];
      const decision = { decision_id: `019d0000-0000-7000-8000-${String(receipts.size + 970).padStart(12, "0")}`,
        rule_candidate_id: values.rule_candidate_id, decision: values.decision, evidence: values.evidence,
        reason: values.reason, reviewer_id: "synthetic-browser-reviewer", created_at: task.updated_at };
      prep.decisions[values.rule_candidate_id] = decision; prep.decision_history.push(decision);
    }
    else if (path.endsWith("/review")) current = { ...current, status: values.decision === "APPROVE" ? "APPROVED" : "REJECTED", review: { ...values, reviewer_id: "synthetic-browser-reviewer", created_at: task.updated_at } };
    else current = { ...task, ...values, status: "QUEUED", opportunities: null, facts: [], materials: [], delivery_hash: null };
    receipts.set(key, { path, body, task: structuredClone(current) });
    if (dropNextReceipt) { dropNextReceipt = false; response.destroy(); return; }
    response.end(JSON.stringify(current)); return;
  }
  response.end(JSON.stringify(path.endsWith("/investigations") ? { tasks: [current] } : current));
});
server.listen(3097, "127.0.0.1");
