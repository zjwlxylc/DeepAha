// Synthetic PostgreSQL result; no WMA, model or official-source requests.
import { readFileSync } from "node:fs";
const fixture = JSON.parse(readFileSync(new URL("../tests/group-inheritance-fixture.json", import.meta.url), "utf8"));
let mode = "normal";
export function handleGroupInheritance(request, response, url) {
  if (url.pathname === "/reset") { mode = "normal"; return false; }
  if (url.pathname === "/seed-group-inheritance") { response.end(JSON.stringify({ task: fixture.dependencies.group_source.source.task_id, plan: fixture.snapshot.base_v2.plan_id })); return true; }
  if (url.pathname === "/group-inheritance-mode") { mode = url.searchParams.get("kind"); response.end("{}"); return true; }
  if (url.pathname.endsWith("/group-inheritance-preview")) {
    const status = { stale: 409, forbidden: 403, unavailable: 503 }[mode];
    response.writeHead(status ?? 200, { "Content-Type": "application/json", "Cache-Control": "private, no-store" });
    response.end(JSON.stringify(status ? { detail: "Synthetic inaccessible projection" } : fixture)); return true;
  }
  return false;
}
