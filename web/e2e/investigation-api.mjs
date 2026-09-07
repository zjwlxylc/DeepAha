// Browser fixtures only. This process never calls an official source or WMA.
import { createServer } from "node:http";
import { source, task } from "../tests/investigations-fixture.ts";

let current = structuredClone(task);
const server = createServer(async (request, response) => {
  const path = new URL(request.url, "http://127.0.0.1:3097").pathname;
  response.setHeader("Content-Type", "application/json");
  if (path === "/reset") { current = structuredClone(task); response.end("{}"); return; }
  if (request.headers.authorization !== "Bearer synthetic-browser-reviewer") {
    response.writeHead(401); response.end("{}"); return;
  }
  if (path.endsWith("/sources")) { response.end(JSON.stringify({ sources: [source] })); return; }
  if (path.includes("/materials/")) {
    response.setHeader("Content-Type", "text/plain");
    response.setHeader("Content-Disposition", 'attachment; filename="original-cccccccccccccccc.xlsx"');
    response.end("synthetic browser fixture; not official material"); return;
  }
  if (request.method === "POST") {
    let body = "";
    for await (const chunk of request) body += chunk;
    const values = JSON.parse(body);
    if (path.endsWith("/review")) current = { ...current, status: values.decision === "APPROVE" ? "APPROVED" : "REJECTED", review: { ...values, reviewer_id: "synthetic-browser-reviewer", created_at: task.updated_at } };
    else current = { ...task, ...values, status: "QUEUED", opportunities: null, facts: [], materials: [], delivery_hash: null };
    response.end(JSON.stringify(current)); return;
  }
  response.end(JSON.stringify(path.endsWith("/investigations") ? { tasks: [current] } : current));
});
server.listen(3097, "127.0.0.1");
