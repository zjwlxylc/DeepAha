import { cookies } from "next/headers";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getPersonalPriorities, PersonalApiError } from "../lib/personal-opportunities";

vi.mock("next/headers", () => ({ cookies: vi.fn() }));

const mockedCookies = vi.mocked(cookies);

describe("personal API client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("forwards the server-only session as bearer and disables caching", async () => {
    mockedCookies.mockResolvedValue({
      get: () => ({ value: "fixture-session-token" }),
    } as Awaited<ReturnType<typeof cookies>>);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ranking_snapshot_id: "019b0000-0000-7000-8000-000000000601",
          items: [],
          omitted_rule_set_count: 0,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await getPersonalPriorities();

    const [url, request] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/api/v1/me/opportunities");
    expect(request?.cache).toBe("no-store");
    expect(new Headers(request?.headers).get("Authorization")).toBe(
      "Bearer fixture-session-token",
    );
  });

  it("fails before network access when the personal session is absent", async () => {
    mockedCookies.mockResolvedValue({ get: () => undefined } as Awaited<
      ReturnType<typeof cookies>
    >);
    const fetchMock = vi.spyOn(globalThis, "fetch");

    await expect(getPersonalPriorities()).rejects.toEqual(
      expect.objectContaining<Partial<PersonalApiError>>({ status: 401 }),
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
