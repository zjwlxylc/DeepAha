// Synthetic PostgreSQL-generated fixture, no WMA or external traffic.
import { readFileSync } from "node:fs";
import { createHash, randomUUID } from "node:crypto";
const sample = JSON.parse(readFileSync(new URL("../tests/group-decisions-fixture.json", import.meta.url), "utf8"));
const fixture = sample.view;
let mode = "normal", posts = 0, mutations = 0, history = [], keys = new Map();
const stable = value => JSON.stringify(value, (_key, item) => item && typeof item === "object" && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : item);
const hash = value => createHash("sha256").update(stable(value)).digest("hex");
export function handleGroupApplicability(request, response, url) {
  const path = url.pathname;
  if (path === "/reset") { mode = "normal"; posts = 0; mutations = 0; history = []; keys = new Map(); return false; }
  if (path === "/group-context-mode") { mode = url.searchParams.get("kind"); response.end("{}"); return true; }
  if (path === "/group-context-receipts") { response.end(JSON.stringify({ posts, mutations })); return true; }
  if (path === "/seed-group-context") { response.end(JSON.stringify(fixture.context)); return true; }
  if (!path.includes(`/investigations/${fixture.context.task_id}/`)) {
    if (path.endsWith("/group-rule-contexts") && request.method === "GET") { response.end("[]"); return true; }
    return false;
  }
  const status = { stale: 409, forbidden: 403, unavailable: 503 }[mode];
  if (status) { response.writeHead(status); response.end("{}"); return true; }
  if (request.method === "POST" && path.endsWith("/group-applicability-decisions")) {
    posts++;
    let bytes = "";
    request.on("data", chunk => { bytes += chunk; });
    request.on("end", () => {
      try {
        const body = JSON.parse(bytes), key = request.headers["idempotency-key"];
        const cached = keys.get(key);
        if (cached) { if (stable(cached.request) !== stable(body)) throw new Error("key conflict"); response.end(JSON.stringify(cached)); return; }
        if (!key || body.context_hash !== fixture.context_hash || body.previous_decision_id !== (history.at(-1)?.decision_id ?? null)) throw new Error("stale");
        const evidence = body.evidence.map(e => {
          const original = sample.saved.history[0].evidence_snapshot.find(b => b.member_id === e.member_id && b.block_id === e.block_id);
          const option = fixture.evidence_options.find(b => b.member_id === e.member_id && b.block_id === e.block_id);
          if (!original || !option?.text.includes(e.quote)) throw new Error("quote");
          return { ...original, quote: e.quote };
        });
        const receipt = { ...sample.saved.history[0], decision_id: randomUUID(), sequence: history.length + 1, request: body, request_hash: hash(body), evidence_snapshot: evidence, evidence_hash: hash(evidence), created_at: new Date().toISOString() };
        history.push(receipt); keys.set(key, receipt); mutations++;
        if (mode === "lost-once") { mode = "normal"; response.writeHead(503); response.end("{}"); return; }
        response.end(JSON.stringify(receipt));
      } catch { response.writeHead(409); response.end("{}"); }
    });
    return true;
  }
  if (request.method !== "GET") { response.writeHead(405); response.end("{}"); return true; }
  if (path.includes("/group-applicability-decisions/")) response.end(JSON.stringify({ ...sample.empty, history, latest: history.at(-1) ?? null }));
  else response.end(JSON.stringify(path.endsWith("/group-rule-contexts") ? [fixture.context] : fixture));
  return true;
}
