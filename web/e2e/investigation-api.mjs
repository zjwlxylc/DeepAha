// Browser fixtures only. This process never calls an official source or WMA.
import { createServer } from "node:http";
import { source, task, preparedDocuments, bindingTarget, evidenceCheck, factPreparation, rulePreparation, ruleReadyTask } from "../tests/investigations-fixture.ts";

let current = structuredClone(task);
let dropNextReceipt = false;
const receipts = new Map();
let posts = 0;
const server = createServer(async (request, response) => {
  const path = new URL(request.url, "http://127.0.0.1:3097").pathname;
  response.setHeader("Content-Type", "application/json");
  if (path === "/reset") { current = structuredClone(task); receipts.clear(); posts = 0; dropNextReceipt = false; response.end("{}"); return; }
  if (path === "/seed-rule-review") { current = ruleReadyTask(); current.rule_review = { current: [], history: [] }; response.end("{}"); return; }
  if (path === "/drop-next-receipt") { dropNextReceipt = true; response.end("{}"); return; }
  if (path === "/receipts") { response.end(JSON.stringify({ mutations: receipts.size, posts })); return; }
  if (request.headers.authorization !== "Bearer synthetic-browser-reviewer") {
    response.writeHead(401); response.end("{}"); return;
  }
  if (path.endsWith("/sources")) { response.end(JSON.stringify({ sources: [source] })); return; }
  if (path.endsWith("/binding-targets")) { response.end(JSON.stringify({ targets: [bindingTarget] })); return; }
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
    if (receipts.has(key)) {
      const receipt = receipts.get(key);
      if (receipt.body !== body || receipt.path !== path) { response.writeHead(409); response.end("{}"); return; }
      response.end(JSON.stringify(receipt.task)); return;
    }
    const values = JSON.parse(body);
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
