// Synthetic PostgreSQL-generated fixture, no WMA or external traffic.
import { readFileSync } from "node:fs";
const fixture = JSON.parse(readFileSync(new URL("../tests/group-applicability-fixture.json", import.meta.url), "utf8"));
let mode = "normal", posts = 0;
export function handleGroupApplicability(request, response, url) {
  const path = url.pathname;
  if (path === "/reset") { mode = "normal"; posts = 0; return false; }
  if (path === "/group-context-mode") { mode = url.searchParams.get("kind"); response.end("{}"); return true; }
  if (path === "/group-context-receipts") { response.end(JSON.stringify({ posts })); return true; }
  if (path === "/seed-group-context") { response.end(JSON.stringify(fixture.context)); return true; }
  if (!path.includes(`/investigations/${fixture.context.task_id}/unit-plans/${fixture.context.target_plan_id}/group-rule-`)) {
    if (path.endsWith("/group-rule-contexts") && request.method === "GET") { response.end("[]"); return true; }
    return false;
  }
  if (request.method !== "GET") { posts++; response.writeHead(405); response.end("{}"); return true; }
  const status = { stale: 409, forbidden: 403, unavailable: 503 }[mode];
  if (status) { response.writeHead(status); response.end("{}"); return true; }
  response.end(JSON.stringify(path.endsWith("/group-rule-contexts") ? [fixture.context] : fixture));
  return true;
}
