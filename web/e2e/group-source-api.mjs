// Synthetic browser state only; no WMA, official downloads or real approvals.
import { groupSourceFixture, groupRecordFixture } from "../tests/group-source-fixture.ts";
import { ruleReadyTask } from "../tests/investigations-fixture.ts";
let data = null, mode = "normal", drop = false, posts = 0;
const records = new Map();
export function resetGroups() { data = null; mode = "normal"; drop = false; posts = 0; records.clear(); }
export function seedGroup() { resetGroups(); data = groupSourceFixture(ruleReadyTask()); return data.task; }
export async function handleGroup(request, response, url) {
  const path = url.pathname;
  if (path === "/group-mode") {
    mode = url.searchParams.get("kind");
    if (mode === "changed") { data.preview.source_hash = "e".repeat(64); data.preview.source.binding_hash = "f".repeat(64); }
    if (mode === "drop") { drop = true; mode = "normal"; }
    response.end("{}"); return true;
  }
  if (path === "/group-receipts") { response.end(JSON.stringify({ posts, mutations: records.size })); return true; }
  if (!path.includes("/group-bindings") && !path.endsWith("/group-source-input")) return false;
  if (request.headers.authorization !== "Bearer synthetic-browser-reviewer") { response.writeHead(401); response.end("{}"); return true; }
  if (request.method === "POST") posts++;
  const status = { stale: 409, forbidden: 403, unavailable: 503 }[mode];
  if (status) { response.writeHead(status); response.end(JSON.stringify({ detail: "synthetic private group failure" })); return true; }
  const prefix = `/api/v1/local-human-test/investigations/${data?.task.task_id}`;
  if (!data || !path.startsWith(`${prefix}/`)) { response.writeHead(404); response.end("{}"); return true; }
  if (request.method === "GET" && path === `${prefix}/group-source-input`) {
    if (url.searchParams.get("entity_id") !== data.preview.source.source_group.id) { response.writeHead(404); response.end("{}"); return true; }
    const registration = [...records.values()].find(record => record.source_hash === data.preview.source_hash) ?? null;
    response.end(JSON.stringify({ ...data.preview, existing_group_id: records.size ? [...records.values()][0].group_identity.unit_id : null, registration })); return true;
  }
  if (request.method === "GET") {
    const record = records.get(path.split("/").at(-1));
    if (!record || record.source_hash !== data.preview.source_hash) { response.writeHead(record ? 409 : 404); response.end("{}"); return true; }
    response.end(JSON.stringify(record)); return true;
  }
  if (request.method === "POST" && path === `${prefix}/group-bindings`) {
    let body = ""; for await (const chunk of request) body += chunk;
    const values = JSON.parse(body);
    if (Object.keys(values).length !== 2 || values.entity_id !== data.preview.source.source_group.id || values.expected_source_hash !== data.preview.source_hash) { response.writeHead(409); response.end("{}"); return true; }
    let record = [...records.values()].find(item => item.source_hash === values.expected_source_hash);
    if (!record) {
      record = groupRecordFixture(data); record.group_binding_id = `019d0000-0000-7000-8000-${String(3101 + records.size).padStart(12, "0")}`;
      record.group_identity.version = records.size + 1;
      records.set(record.group_binding_id, structuredClone(record));
    }
    if (drop) { drop = false; response.destroy(); return true; }
    response.end(JSON.stringify(record)); return true;
  }
  response.writeHead(404); response.end("{}"); return true;
}
