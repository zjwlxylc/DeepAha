import { beforeEach, describe, expect, it, vi } from "vitest";

import { humanTestFetch } from "../lib/local-human-test";

const cookieGet = vi.fn();

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: cookieGet }),
}));

describe("local human test API client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    cookieGet.mockReturnValue({ value: "local-reviewer-session" });
  });

  it("keeps reviewer authentication server-side and disables caching", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ configured: false }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await humanTestFetch("/config/provider");

    const [, request] = fetchMock.mock.calls[0];
    expect(new Headers(request?.headers).get("Authorization")).toBe(
      "Bearer local-reviewer-session",
    );
    expect(request?.cache).toBe("no-store");
  });

  it("returns a generic error without exposing an upstream body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("provider secret and upstream body", { status: 409 }),
    );

    await expect(humanTestFetch("/runs")).rejects.toMatchObject({
      status: 409,
      message: "Local human test request failed",
    });
  });
});
