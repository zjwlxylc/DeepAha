import { beforeEach, describe, expect, it, vi } from "vitest";

import { addMaterialAction } from "../app/personal-actions";
import { personalFetch } from "../lib/personal-opportunities";
import { personalDetail, publicId } from "./personal-fixtures";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: vi.fn() }));
vi.mock("../lib/personal-opportunities", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/personal-opportunities")>();
  return { ...original, personalFetch: vi.fn() };
});

const mockedPersonalFetch = vi.mocked(personalFetch);

describe("personal action server mutations", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("appends a material item to the server-authoritative plan", async () => {
    const existingItem = {
      material_item_id: "019b0000-0000-7000-8000-000000000631",
      label: "既有身份证明",
      completed: false,
      due_on: null,
    };
    mockedPersonalFetch
      .mockResolvedValueOnce({
        ...personalDetail,
        action: {
          action_snapshot_id: "019b0000-0000-7000-8000-000000000632",
          action_id: "019b0000-0000-7000-8000-000000000633",
          version: 1,
          opportunity_id: personalDetail.eligibility.opportunity_id,
          opportunity_version: 2,
          saved: true,
          state: "PREPARING",
          material_items: [existingItem],
          last_event_id: "019b0000-0000-7000-8000-000000000634",
          input_sha256: "7".repeat(64),
          created_at: "2026-08-22T09:00:00Z",
        },
      })
      .mockResolvedValueOnce({} as never);

    const formData = new FormData();
    formData.set("public_id", publicId);
    formData.set("material_label", "新增报名表");
    formData.set("material_due_on", "2026-09-10");

    await addMaterialAction(formData);

    expect(mockedPersonalFetch).toHaveBeenCalledTimes(2);
    const [, request] = mockedPersonalFetch.mock.calls[1];
    const body = JSON.parse(String(request?.body)) as {
      items: Array<{ label: string; due_on: string | null }>;
    };
    expect(body.items).toHaveLength(2);
    expect(body.items[0]).toEqual(existingItem);
    expect(body.items[1]).toEqual(
      expect.objectContaining({ label: "新增报名表", due_on: "2026-09-10" }),
    );
  });
});
