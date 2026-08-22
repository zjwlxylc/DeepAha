import { afterEach, describe, expect, it, vi } from "vitest";

import { listPublicOpportunities } from "../lib/public-opportunities";
import { publicPage } from "./fixtures";


describe("public API client recovery", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not cache a failed catalog response across explicit retries", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(publicPage), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await listPublicOpportunities({ q: "recovery-check" });

    const [request, options] = fetchMock.mock.calls[0];
    expect(String(request)).toContain("/api/v1/public/opportunities?q=recovery-check");
    expect(options).toEqual(expect.objectContaining({ cache: "no-store" }));
  });
});
