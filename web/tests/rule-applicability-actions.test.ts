import { beforeEach, describe, expect, it, vi } from "vitest";
import { loadRuleApplicabilityAction, saveRuleApplicabilityAction } from "../app/review/investigations/rule-applicability-actions";
import { unitSnapshotFixture } from "./investigations-fixture";
import { applicabilityDecisionFixture, applicabilityIds, applicabilityViewFixture } from "./rule-applicability-fixture";

vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "synthetic-reviewer-session" }) }) }));
const { identity, view } = applicabilityViewFixture(unitSnapshotFixture());
const decision = applicabilityDecisionFixture(view), request = decision.request;
beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(decision)); });

describe("applicability actions", () => {
  it("preserves exact quotes and reuses the request key after a lost receipt", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error("private exception must not leak"));
    expect(await saveRuleApplicabilityAction(identity, request, applicabilityIds.member)).toMatchObject({ ok: false, kind: "unavailable" });
    expect(await saveRuleApplicabilityAction(identity, request, applicabilityIds.member)).toEqual({ ok: true, value: decision });
    const [first, second] = vi.mocked(fetch).mock.calls;
    expect(second[1]!.body).toEqual(first[1]!.body);
    expect(second[1]!.headers).toEqual(first[1]!.headers);
    expect(JSON.parse(second[1]!.body as string).evidence[0].quote).toBe(view.evidence_options[0].text);
    expect(second[1]!.cache).toBe("no-store");
  });
  it("binds the key to the target, source, predecessor and complete request", async () => {
    await saveRuleApplicabilityAction(identity, request, applicabilityIds.member);
    const other = { ...identity, target_plan_id: applicabilityIds.secondBlock };
    const changed = { ...request, target_plan_id: other.target_plan_id, previous_decision_id: applicabilityIds.decision, outcome: "DOES_NOT_APPLY" as const };
    vi.mocked(fetch).mockResolvedValue(Response.json({ ...decision, request: changed }));
    await saveRuleApplicabilityAction(other, changed, applicabilityIds.member);
    const [first, second] = vi.mocked(fetch).mock.calls;
    expect((first[1]!.headers as Record<string, string>)["Idempotency-Key"]).not.toEqual((second[1]!.headers as Record<string, string>)["Idempotency-Key"]);
  });
  it.each(["empty_reason", "empty_evidence", "empty_quote", "too_long_quote", "too_many", "wrong_target", "missing_nonce"])("rejects %s before sending", invalid => {
    const changed = structuredClone(request);
    if (invalid === "empty_reason") changed.reason = "   ";
    if (invalid === "empty_evidence") changed.evidence = [];
    if (invalid === "empty_quote") changed.evidence[0].quote = "\n ";
    if (invalid === "too_long_quote") changed.evidence[0].quote = "x".repeat(20001);
    if (invalid === "too_many") changed.evidence = Array(21).fill(changed.evidence[0]);
    if (invalid === "wrong_target") changed.target_plan_id = applicabilityIds.secondBlock;
    return saveRuleApplicabilityAction(identity, changed, invalid === "missing_nonce" ? "" : applicabilityIds.member).then(result => {
      expect(result.ok).toBe(false); expect(fetch).not.toHaveBeenCalled();
    });
  });
  it("allows an explicit unresolved decision without evidence", async () => {
    const pending = applicabilityDecisionFixture(view, { outcome: "NEEDS_ADJUDICATION", evidence: [], reason: "仍需核对附件中的例外" });
    vi.mocked(fetch).mockResolvedValue(Response.json(pending));
    expect(await saveRuleApplicabilityAction(identity, pending.request, applicabilityIds.member)).toEqual({ ok: true, value: pending });
  });
  it.each([[403, "forbidden"], [409, "stale"], [503, "unavailable"]])("returns only a safe error for HTTP %s", async (status, kind) => {
    vi.mocked(fetch).mockResolvedValue(Response.json({ detail: "private exception" }, { status: status as number }));
    const result = await saveRuleApplicabilityAction(identity, request, applicabilityIds.member);
    expect(result).toMatchObject({ ok: false, kind }); expect(JSON.stringify(result)).not.toContain("private exception");
  });
  it("loads more evidence using the server cursor and no-store", async () => {
    vi.mocked(fetch).mockResolvedValue(Response.json(view));
    expect(await loadRuleApplicabilityAction(identity, view.next_cursor)).toEqual({ ok: true, value: view });
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain(`?${new URLSearchParams({ after: view.next_cursor! })}`);
    expect(vi.mocked(fetch).mock.calls[0][1]!.cache).toBe("no-store");
  });
  it("rejects a response belonging to another source rule", async () => {
    vi.mocked(fetch).mockResolvedValue(Response.json({ ...view, context: { ...view.context, source_rule_candidate_id: applicabilityIds.secondBlock } }));
    expect((await loadRuleApplicabilityAction(identity)).ok).toBe(false);
  });
});
