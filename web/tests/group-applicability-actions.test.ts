import { beforeEach, describe, expect, it, vi } from "vitest";
import fixture from "./group-applicability-fixture.json";
import { humanTestFetch, LocalHumanTestApiError } from "../lib/local-human-test";
import { loadGroupApplicabilityAction, loadGroupApplicabilityEntries } from "../app/review/investigations/group-applicability-actions";
vi.mock("../lib/local-human-test", () => ({ humanTestFetch: vi.fn(), LocalHumanTestApiError: class extends Error { constructor(public status: number) { super(); } } }));
const identity = fixture.context;
beforeEach(() => { vi.mocked(humanTestFetch).mockReset(); });
describe("read-only group applicability", () => {
  it("accepts the actual PostgreSQL synthetic receipt", async () => {
    vi.mocked(humanTestFetch).mockResolvedValue(fixture);
    expect(await loadGroupApplicabilityAction(identity)).toEqual({ ok: true, value: fixture });
    expect(humanTestFetch).toHaveBeenCalledOnce();
  });
  it.each(["hash", "target", "approval", "outcome", "candidate", "cursor"])("hides inconsistent %s", field => {
    const value = structuredClone(fixture);
    if (field === "hash") value.context_hash = "a".repeat(64);
    if (field === "target") value.context.target.unit_id = identity.task_id;
    if (field === "approval") value.approval.decision = "REJECT";
    if (field === "outcome") value.outcome = "APPLIES";
    if (field === "candidate") value.candidate.rule_candidate_id = identity.task_id;
    if (field === "cursor") Object.assign(value, { next_cursor: identity.task_id });
    vi.mocked(humanTestFetch).mockResolvedValue(value);
    return expect(loadGroupApplicabilityAction(identity)).resolves.toMatchObject({ ok: false });
  });
  it.each([403, 409, 503])("hides content on HTTP %i", async status => {
    vi.mocked(humanTestFetch).mockRejectedValue(new LocalHumanTestApiError(status));
    expect(await loadGroupApplicabilityAction(identity)).toMatchObject({ ok: false });
  });
  it("rejects invalid identity and cursor without fetching", async () => {
    expect(await loadGroupApplicabilityAction({ ...identity, task_id: "bad" })).toMatchObject({ ok: false });
    expect(await loadGroupApplicabilityAction(identity, "bad")).toMatchObject({ ok: false });
    expect(humanTestFetch).not.toHaveBeenCalled();
  });
  it("discovers only exact current identities", async () => {
    vi.mocked(humanTestFetch).mockResolvedValue([identity]);
    expect(await loadGroupApplicabilityEntries(identity.task_id, identity.target_plan_id)).toEqual({ ok: true, value: [identity] });
    vi.mocked(humanTestFetch).mockResolvedValue([{ ...identity, task_id: identity.target_plan_id }]);
    expect(await loadGroupApplicabilityEntries(identity.task_id, identity.target_plan_id)).toMatchObject({ ok: false });
  });
});
