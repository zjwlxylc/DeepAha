import { beforeEach, describe, expect, it, vi } from "vitest";
import fixture from "./group-decisions-fixture.json";
import { humanTestFetch, LocalHumanTestApiError } from "../lib/local-human-test";
import { postInvestigation } from "../lib/investigations";
import { loadGroupApplicabilityReview, saveGroupApplicabilityDecision } from "../app/review/investigations/group-applicability-decision-actions";
import type { GroupApplicabilityHistory, GroupApplicabilityRequest } from "../lib/group-applicability-decisions";
vi.mock("../lib/local-human-test", () => ({ humanTestFetch: vi.fn(), LocalHumanTestApiError: class extends Error { constructor(public status: number) { super(); } } }));
vi.mock("../lib/investigations", () => ({ postInvestigation: vi.fn(), InvestigationApiError: class extends Error { constructor(public status: number) { super(); } } }));
const identity = fixture.view.context, first = fixture.saved.history[0];
const request = first.request as GroupApplicabilityRequest;
beforeEach(() => vi.clearAllMocks());
describe("group applicability decision actions", () => {
  it("combines matching current context and actual database history", async () => {
    vi.mocked(humanTestFetch).mockResolvedValueOnce(fixture.view).mockResolvedValueOnce(fixture.saved);
    expect(await loadGroupApplicabilityReview(identity)).toEqual({ ok: true, value: { ...fixture.view, decisions: fixture.saved } });
  });
  it.each(["context", "latest", "request", "evidence"])("hides invalid %s history", async field => {
    const changed = structuredClone(fixture.saved) as unknown as GroupApplicabilityHistory;
    if (field === "context") changed.context_hash = "f".repeat(64);
    if (field === "latest") changed.latest = changed.history[0];
    if (field === "request") changed.history[0].request.reason = "forged";
    if (field === "evidence") changed.history[0].evidence_snapshot[0].quote = "rewritten";
    vi.mocked(humanTestFetch).mockResolvedValueOnce(fixture.view).mockResolvedValueOnce(changed);
    expect(await loadGroupApplicabilityReview(identity)).toMatchObject({ ok: false });
  });
  it("retries the same request with the same idempotency key", async () => {
    vi.mocked(postInvestigation).mockRejectedValueOnce(new Error("lost receipt")).mockResolvedValueOnce(first);
    expect(await saveGroupApplicabilityDecision(identity, request, identity.task_id)).toMatchObject({ ok: false });
    expect(await saveGroupApplicabilityDecision(identity, request, identity.task_id)).toEqual({ ok: true, value: first });
    expect(vi.mocked(postInvestigation).mock.calls[0]).toEqual(vi.mocked(postInvestigation).mock.calls[1]);
  });
  it.each([403, 409, 503])("hides history when its HTTP %i read fails", async status => {
    vi.mocked(humanTestFetch).mockResolvedValueOnce(fixture.view).mockRejectedValueOnce(new LocalHumanTestApiError(status));
    expect(await loadGroupApplicabilityReview(identity)).toMatchObject({ ok: false });
  });
  it("rejects a mismatched save receipt", async () => {
    vi.mocked(postInvestigation).mockResolvedValue({ ...first, request_hash: "f".repeat(64) });
    expect(await saveGroupApplicabilityDecision(identity, request, identity.task_id)).toMatchObject({ ok: false });
  });
});
