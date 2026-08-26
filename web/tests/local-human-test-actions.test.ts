import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createHumanTestRunAction,
  saveProviderConfigAction,
} from "../app/review/human-test/actions";
import { humanTestFetch } from "../lib/local-human-test";

vi.mock("../lib/local-human-test", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/local-human-test")>();
  return { ...original, humanTestFetch: vi.fn() };
});

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

describe("local human test server actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(humanTestFetch).mockResolvedValue({} as never);
  });

  it("sends a new idempotency key and never returns the Provider secret", async () => {
    const data = new FormData();
    data.set("provider", "agnes");
    data.set("base_url", "https://provider.invalid");
    data.set("protocol", "openai_chat_completions");
    data.set("model_id", "agnes-chat");
    data.set("model_snapshot", "agnes-chat-2026-08-26");
    data.set("provider_region", "cn");
    data.set("zero_retention", "on");
    data.set("supports_idempotency", "on");
    data.set("api_key", "must-not-return-this-secret");

    const result = await saveProviderConfigAction(
      { error: null, message: null },
      data,
    );

    expect(result).toEqual({ error: null, message: "Provider 配置已安全保存。" });
    expect(JSON.stringify(result)).not.toContain("must-not-return-this-secret");
    const [, request] = vi.mocked(humanTestFetch).mock.calls[0];
    expect(new Headers(request?.headers).get("Idempotency-Key")).toMatch(/^[0-9a-f-]+$/);
    expect(JSON.parse(String(request?.body)).api_key).toBe(
      "must-not-return-this-secret",
    );
  });

  it("refuses live work unless the source and budget confirmation is present", async () => {
    const data = new FormData();
    data.set("mode", "LIVE_OFFICIAL");
    data.set("recipe_id", "019d0000-0000-7000-8000-000000000901");

    const result = await createHumanTestRunAction(
      { error: null, message: null },
      data,
    );

    expect(result.error).toMatch(/确认来源与硬预算/);
    expect(humanTestFetch).not.toHaveBeenCalled();
  });
});
