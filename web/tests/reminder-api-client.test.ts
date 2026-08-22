import { cookies } from "next/headers";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getDeadlineReminderPreference,
  getReminderInbox,
  setDeadlineReminderPreference,
} from "../lib/reminders";

vi.mock("next/headers", () => ({ cookies: vi.fn() }));

const mockedCookies = vi.mocked(cookies);

describe("reminder API client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockedCookies.mockResolvedValue({
      get: () => ({ value: "phase8-fixture-session" }),
    } as Awaited<ReturnType<typeof cookies>>);
  });

  it("uses exact private GET paths with bearer forwarding and no-store", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(null), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await getDeadlineReminderPreference();
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [], count: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await getReminderInbox();

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "http://127.0.0.1:8000/api/v1/me/reminder-preferences/deadline-change",
      "http://127.0.0.1:8000/api/v1/me/reminder-inbox",
    ]);
    for (const [, request] of fetchMock.mock.calls) {
      expect(request?.cache).toBe("no-store");
      expect(new Headers(request?.headers).get("Authorization")).toBe(
        "Bearer phase8-fixture-session",
      );
    }
  });

  it("writes only enabled with the caller supplied idempotency key", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ enabled: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await setDeadlineReminderPreference(true, "phase8-idempotency-key");

    const [url, request] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(
      "http://127.0.0.1:8000/api/v1/me/reminder-preferences/deadline-change",
    );
    expect(request?.method).toBe("PUT");
    expect(JSON.parse(String(request?.body))).toEqual({ enabled: true });
    expect(new Headers(request?.headers).get("Idempotency-Key")).toBe(
      "phase8-idempotency-key",
    );
  });
});
