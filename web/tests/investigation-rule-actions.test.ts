import { beforeEach, describe, expect, it, vi } from "vitest";
import { investigationRuleAction } from "../app/review/investigations/actions";
import { rulePreparation as prep, task, taskId } from "./investigations-fixture";
import { isExplicitRuleTime } from "../lib/investigation-rule-options";

vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "synthetic-reviewer-session" }) }) }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
const empty = { error: null, message: null, taskId: null };
const ref = prep.rows[0].evidence_ref_ids[0];
function form() {
  const data = new FormData();
  Object.entries({ request_key: taskId, task_id: taskId, delivery_hash: prep.delivery_hash,
    binding_id: prep.binding_id, check_id: prep.check_id, fact_preparation_id: prep.fact_preparation_id,
    fact_set_id: prep.fact_set_id, entity_id: prep.entity_id, rule_preparation_id: prep.rule_preparation_id,
    rule_candidate_id: prep.rows[0].rule_candidate_id!, kind: "decision", decision: "APPROVE",
    reason: "合成审核，不代表真人审批", evidence_ref_id: ref,
    [`authority:${ref}`]: "FORMAL_OFFICIAL_ATTACHMENT", [`relation:${ref}`]: "SUPPORTS",
    [`applicability:${ref}`]: "APPLIES_TO_EXACT_TARGET", [`effective_at:${ref}`]: "2026-09-07T10:30:00+08:00",
    [`evidence_reason:${ref}`]: "合成证据审查",
  }).forEach(([name, value]) => data.set(name, value));
  return data;
}
describe("rule actions", () => {
  beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(task)); });
  it("sends the exact current fact and check identities and reuses the key after a lost response", async () => {
    const data = form();
    vi.mocked(fetch).mockRejectedValueOnce(new Error("lost"));
    expect((await investigationRuleAction(empty, data)).error).toBeTruthy();
    expect((await investigationRuleAction(empty, data)).message).toContain("独立规则审核已记录");
    const [first, second] = vi.mocked(fetch).mock.calls;
    expect(second[1]!.headers).toEqual(first[1]!.headers);
    expect(second[1]!.body).toEqual(first[1]!.body);
    expect(JSON.parse(second[1]!.body as string)).toMatchObject({ check_id: prep.check_id,
      fact_set_id: prep.fact_set_id, evidence: [{ effective_at: "2026-09-07T10:30:00+08:00", evidence_ref_id: ref }] });
  });
  it.each(["authority", "relation", "effective_at", "applicability"])("cannot approve with missing %s", async key => {
    const data = form(); data.set(`${key}:${ref}`, key === "applicability" ? "UNRESOLVED" : "");
    expect((await investigationRuleAction(empty, data)).error).toBeTruthy(); expect(fetch).not.toHaveBeenCalled();
  });
  it.each(["REJECT", "NEEDS_ADJUDICATION"])("retains unresolved evidence on %s without invented authority or time", async decision => {
    const data = form(); data.set("decision", decision);
    for (const field of ["authority", "relation", "effective_at"]) data.set(`${field}:${ref}`, "");
    data.set(`applicability:${ref}`, "UNRESOLVED");
    expect((await investigationRuleAction(empty, data)).error).toBeNull();
    const body = JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string);
    expect(body.evidence[0]).toMatchObject({ authority: null, relation: null, effective_at: null, applicability: "UNRESOLVED" });
  });
  it("rejects duplicate evidence and a stale preparation without submitting", async () => {
    const data = form(); data.append("evidence_ref_id", ref);
    expect((await investigationRuleAction(empty, data)).error).toContain("证据清单");
    data.set("evidence_ref_id", ref); data.set("check_id", "");
    expect((await investigationRuleAction(empty, data)).error).toContain("核验回执");
    expect(fetch).not.toHaveBeenCalled();
  });
  it("prepares candidates without a decision or evidence assessment", async () => {
    const data = form(); data.set("kind", "prepare");
    expect((await investigationRuleAction(empty, data)).message).toContain("尚未批准");
    const [url, request] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toMatch(/\/rules$/); expect(JSON.parse(request!.body as string)).not.toHaveProperty("decision");
  });
});
describe("explicit rule time", () => {
  it.each(["2026-09-07", "2026-02-29T10:00:00+08:00", "2026-04-31T10:00:00Z", "2026-09-07T10:00", "2026-09-07T24:00:00Z"])("rejects %s", value => expect(isExplicitRuleTime(value)).toBe(false));
  it.each(["2024-02-29T10:00:00+08:00", "2026-09-07T02:30:00Z"])("accepts %s", value => expect(isExplicitRuleTime(value)).toBe(true));
});
