import { revalidatePath } from "next/cache";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { toggleDeadlineReminderAction } from "../app/reminder-actions";
import { setDeadlineReminderPreference } from "../lib/reminders";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("../lib/reminders", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/reminders")>();
  return { ...original, setDeadlineReminderPreference: vi.fn() };
});

const mockedSetPreference = vi.mocked(setDeadlineReminderPreference);
const mockedRevalidate = vi.mocked(revalidatePath);

describe("deadline reminder action", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedSetPreference.mockResolvedValue({} as never);
  });

  it("uses a fresh key and revalidates only the reminder route", async () => {
    const formData = new FormData();
    formData.set("enabled", "true");

    await toggleDeadlineReminderAction(formData);
    await toggleDeadlineReminderAction(formData);

    expect(mockedSetPreference).toHaveBeenNthCalledWith(
      1,
      true,
      expect.stringMatching(/^[0-9a-f-]{36}$/),
    );
    expect(mockedSetPreference).toHaveBeenNthCalledWith(
      2,
      true,
      expect.stringMatching(/^[0-9a-f-]{36}$/),
    );
    const firstKey = mockedSetPreference.mock.calls[0][1];
    const secondKey = mockedSetPreference.mock.calls[1][1];
    expect(firstKey).not.toBe(secondKey);
    expect(mockedRevalidate).toHaveBeenCalledTimes(2);
    expect(mockedRevalidate.mock.calls).toEqual([
      ["/me/reminders"],
      ["/me/reminders"],
    ]);
  });

  it("accepts Next.js server-action metadata without forwarding it", async () => {
    const formData = new FormData();
    formData.set("$ACTION_ID_phase8", "framework-only");
    formData.set("enabled", "on");

    await toggleDeadlineReminderAction(formData);

    expect(mockedSetPreference).toHaveBeenCalledWith(true, expect.any(String));
    expect(mockedRevalidate).toHaveBeenCalledWith("/me/reminders");
  });

  it.each(["cadence", "target", "user_id"])("rejects extra %s fields", async (field) => {
    const formData = new FormData();
    formData.set("enabled", "false");
    formData.set(field, "untrusted-value");

    await expect(toggleDeadlineReminderAction(formData)).rejects.toThrow(
      "Invalid reminder preference form",
    );
    expect(mockedSetPreference).not.toHaveBeenCalled();
    expect(mockedRevalidate).not.toHaveBeenCalled();
  });
});
