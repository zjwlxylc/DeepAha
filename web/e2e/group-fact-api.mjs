// Synthetic browser mechanics; never real evidence or human approval.
import { groupFactFixture, fixtureHash } from "../tests/group-fact-fixture.ts";
import { groupSourceFixture, groupRecordFixture } from "../tests/group-source-fixture.ts";
import { ruleReadyTask } from "../tests/investigations-fixture.ts";
import { groupRuleFixture } from "../tests/group-rule-fixture.ts";
let rulePreview = null;
let data = null, mode = "normal", prepared = false, drop = false, posts = 0;
const receipts = new Map();
export function resetGroupFacts() { data = null; rulePreview = null; mode = "normal"; prepared = false; drop = false; posts = 0; receipts.clear(); }
export function seedGroupRules() { seedGroupFacts(); prepared = true; rulePreview = groupRuleFixture(data); return data; }
export function seedGroupFacts(legacy = false) {
  resetGroupFacts(); const source = groupSourceFixture(ruleReadyTask()); data = groupFactFixture(source, groupRecordFixture(source));
  if (legacy) {
    data.source.task.facts = structuredClone(data.source.task.facts);
    for (const row of data.record.result.rows) delete row.original.note;
    const peer = { ...data.source.task.facts[3] }; delete peer.note;
    data.record.result.excluded_rows[0].source_hash = fixtureHash(peer);
    data.record.result_hash = fixtureHash(data.record.result);
  }
  return data;
}
export async function handleGroupFacts(request, response, url) {
  const path = url.pathname;
  if (path === "/group-fact-mode") { mode = url.searchParams.get("kind"); if (mode === "drop") { drop = true; mode = "normal"; } response.end("{}"); return true; }
  if (path === "/group-fact-receipts") { response.end(JSON.stringify({ posts, mutations: receipts.size })); return true; }
  if (!data || (!path.includes("/group-facts/") && !path.includes("/group-bindings/"))) return false;
  if (request.headers.authorization !== "Bearer synthetic-browser-reviewer") { response.writeHead(401); response.end("{}"); return true; }
  if (request.method === "POST") posts++;
  const status = { stale: 409, forbidden: 403, unavailable: 503 }[mode];
  if (status) { response.writeHead(status); response.end('{"detail":"synthetic private failure"}'); return true; }
  const root = `/api/v1/local-human-test/investigations/${data.source.task.task_id}`, group = data.source.preview.registration;
  if (request.method === "GET") {
    if (rulePreview && path === `${root}/group-facts/${data.record.preparation_id}/rules/preview`) response.end(JSON.stringify(rulePreview));
    else if (path === `${root}/group-bindings/${group.group_binding_id}`) response.end(JSON.stringify(group));
    else if (prepared && path === `${root}/group-facts/${data.record.preparation_id}`) response.end(JSON.stringify(data.record));
    else { response.writeHead(404); response.end("{}"); }
    return true;
  }
  let raw = ""; for await (const chunk of request) raw += chunk;
  const body = JSON.parse(raw), key = request.headers["idempotency-key"];
  if (receipts.has(key)) {
    if (receipts.get(key) !== raw) { response.writeHead(409); response.end("{}"); return true; }
  } else if (path === `${root}/group-bindings/${group.group_binding_id}/facts`) {
    if (body.check_id !== data.record.result.check_id || body.expected_source_hash !== group.source_hash) { response.writeHead(409); response.end("{}"); return true; }
    prepared = true; receipts.set(key, raw);
  } else if (prepared && path === `${root}/group-facts/${data.record.preparation_id}/decisions`) {
    const row = data.record.result.rows.find(row => row.candidate_id === body.candidate_id);
    if (!row || body.expected_preparation_hash !== data.record.result_hash || (row.abstained && body.decision === "APPROVE")) { response.writeHead(409); response.end("{}"); return true; }
    const decision = { candidate_id: body.candidate_id, decision_id: `019d0000-0000-7000-8000-${String(5000 + receipts.size).padStart(12, "0")}`, decision: body.decision, reason: body.reason, reviewer_id: data.record.reviewer_id, created_at: data.record.created_at };
    data.record.decisions[body.candidate_id] = decision; data.record.history.push(decision); receipts.set(key, raw);
  } else if (prepared && path === `${root}/group-facts/${data.record.preparation_id}/promotions`) {
    const candidates = data.record.result.rows.filter(row => row.candidate_id);
    if (body.expected_preparation_hash !== data.record.result_hash || candidates.some(row => !data.record.decisions[row.candidate_id] || data.record.decisions[row.candidate_id].decision === "NEEDS_ADJUDICATION")) { response.writeHead(409); response.end("{}"); return true; }
    data.record.fact_set = { fact_set_id: "019d0000-0000-7000-8000-000000005099", status: "ACTIVE", version: 1, reason: body.reason }; receipts.set(key, raw);
  } else { response.writeHead(404); response.end("{}"); return true; }
  if (drop) { drop = false; response.destroy(); return true; }
  response.end(JSON.stringify(data.record)); return true;
}
