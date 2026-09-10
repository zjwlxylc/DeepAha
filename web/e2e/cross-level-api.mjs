// Actual synthetic PG export; no external investigation or model invocation.
import { readFileSync } from "node:fs";
const fixture = JSON.parse(readFileSync(new URL("../tests/cross-level-fixture.json", import.meta.url), "utf8"));
let mode = "normal";
export function handleCrossLevel(request, response, url) {
  if (url.pathname === "/reset") { mode = "normal"; return false; }
  if (url.pathname === "/seed-cross-level") { response.end(JSON.stringify({ task: fixture.dependencies.group.dependencies.group_source.source.task_id, plan: fixture.dependencies.group.snapshot.base_v2.plan_id })); return true; }
  if (url.pathname === "/cross-level-mode") { mode = url.searchParams.get("kind"); response.end("{}"); return true; }
  if (url.pathname.endsWith("/cross-level-preview")) {
    const status = { stale: 409, forbidden: 403, unavailable: 503 }[mode];
    response.writeHead(status ?? 200, { "Content-Type": "application/json", "Cache-Control": "private, no-store" });
    response.end(JSON.stringify(status ? { detail: "Synthetic inaccessible snapshot" } : fixture)); return true;
  }
  return false;
}
