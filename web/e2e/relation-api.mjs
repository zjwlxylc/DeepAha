// Real synthetic PostgreSQL exports; browser simulation never calls WMA.
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { isDeepStrictEqual } from "node:util";
const f = JSON.parse(readFileSync(new URL("../tests/relation-review-fixture.json", import.meta.url), "utf8"));
const n = JSON.parse(readFileSync(new URL("../tests/relation-proposal-fixture.json", import.meta.url), "utf8"));
let current = f.saved;
createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1:3099");
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Cache-Control", "private, no-store");
  if (url.pathname === "/reset") { current = f.saved; res.end("{}"); return; }
  if (url.pathname === "/stale") { current = structuredClone(current); current.review.status = "STALE"; res.end("{}"); return; }
  if (url.pathname.includes(n.task)) {
    if (url.pathname.endsWith("/cross-level-preview")) { res.end(JSON.stringify(n.context.review)); return; }
    if (url.pathname.endsWith("/relation-proposal-context")) { res.end(JSON.stringify(n.context)); return; }
    if (url.pathname.endsWith("/relation-proposals") && req.method === "POST") {
      let raw = ""; for await (const part of req) raw += part;
      if (!req.headers["idempotency-key"] || !isDeepStrictEqual(JSON.parse(raw), n.command)) { res.writeHead(409); res.end("{}"); return; }
      res.end(JSON.stringify(n.saved)); return;
    }
    if (url.pathname.endsWith(`/relation-proposals/${n.saved.proposal_id}`)) { res.end(JSON.stringify(n.saved)); return; }
  }
  if (url.pathname.endsWith("/relation-decisions") && req.method === "POST") {
    let raw = ""; for await (const part of req) raw += part;
    const command = JSON.parse(raw);
    if (command.decision !== "APPROVE" || command.reason !== f.approved.decision.reason || command.expected_proposal_payload_hash !== f.saved.proposal_payload_sha256) { res.writeHead(409); res.end("{}"); return; }
    current = f.approved; res.end(JSON.stringify(current)); return;
  }
  if (url.pathname.endsWith("/relation-proposals")) { res.end(JSON.stringify({ task_id: f.task, target_plan_id: f.plan, proposals: [{ proposal_id: f.saved.proposal_id, producer_id: f.saved.package.proposal.producer_id, created_at: f.saved.package.proposal.created_at }] })); return; }
  if (url.pathname.endsWith(`/relation-proposals/${f.saved.proposal_id}`)) { res.end(JSON.stringify(current)); return; }
  res.writeHead(404); res.end("{}");
}).listen(3099, "127.0.0.1");
