import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HumanTestPage from "../app/review/human-test/page";
import ProviderConfigForm from "../components/human-test/provider-config-form";
import RunForm from "../components/human-test/run-form";

vi.mock("../lib/local-human-test", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/local-human-test")>();
  return {
    ...original,
    getLocalProviderStatus: vi.fn(),
    getLocalSources: vi.fn(),
    getLocalRuns: vi.fn(),
  };
});

import {
  getLocalProviderStatus,
  getLocalRuns,
  getLocalSources,
  type LocalSource,
} from "../lib/local-human-test";

const source: LocalSource = {
  recipe_id: "019d0000-0000-7000-8000-000000000901",
  source_id: "019d0000-0000-7000-8000-000000000902",
  endpoint_id: "019d0000-0000-7000-8000-000000000903",
  authority_name: "浙江省示例主管部门",
  jurisdiction: "浙江省",
  usage_role: "PRIMARY_EVIDENCE",
  official_url: "https://official.example.gov.cn/notices",
  official_host: "official.example.gov.cn",
  verified_at: "2026-08-26T10:00:00Z",
  maximum_requests: 3,
  opportunity_type_hint: "RESEARCH_PROGRAM",
};

describe("local human test console", () => {
  beforeEach(() => {
    vi.mocked(getLocalProviderStatus).mockResolvedValue({
      configured: true,
      provider: "agnes",
      base_url: "https://provider.invalid",
      protocol: "openai_chat_completions",
      model_id: "agnes-chat",
      model_snapshot: "agnes-chat-2026-08-26",
      provider_region: "cn",
      zero_retention: true,
      training_use: false,
      supports_idempotency: true,
      egress_ready: true,
      updated_at: "2026-08-26T10:00:00Z",
    });
    vi.mocked(getLocalSources).mockResolvedValue([source]);
    vi.mocked(getLocalRuns).mockResolvedValue([]);
  });

  it("states the evidence boundary and never renders a stored secret", async () => {
    render(await HumanTestPage());

    expect(screen.getByText("Release Qualification：NOT_STARTED")).toBeVisible();
    expect(screen.getByText("真人参与者：0")).toBeVisible();
    expect(screen.getByText("LOCAL_HUMAN_REVIEWED")).toBeVisible();
    expect(screen.getByText("已保存，可真实运行")).toBeVisible();
    expect(screen.queryByDisplayValue(/secret/i)).not.toBeInTheDocument();
  });

  it("requires an explicit live budget confirmation", async () => {
    render(<RunForm sources={[source]} providerReady />);
    const live = screen.getByRole("radio", { name: /受控实时采集/ });
    fireEvent.click(live);

    const button = screen.getByRole("button", { name: "开始受控真实运行" });
    expect(button).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /确认来源与硬预算/ }));
    expect(button).toBeEnabled();
  });

  it("offers public Provider presets without pre-claiming unverified capabilities", () => {
    render(
      <ProviderConfigForm
        status={{
          configured: false,
          provider: null,
          base_url: null,
          protocol: null,
          model_id: null,
          model_snapshot: null,
          provider_region: null,
          zero_retention: null,
          training_use: null,
          supports_idempotency: null,
          egress_ready: false,
          updated_at: null,
        }}
      />,
    );

    expect(screen.getByLabelText("Provider 名称")).toHaveValue("agnes");
    expect(screen.getByLabelText("HTTPS Base URL")).toHaveValue(
      "https://apihub.agnes-ai.com/v1",
    );
    expect(screen.getByLabelText("模型 ID")).toHaveValue("agnes-2.5-flash");
    expect(screen.getByRole("checkbox", { name: /零保留/ })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /不用于模型训练/ })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /幂等请求身份/ })).not.toBeChecked();

    fireEvent.change(screen.getByLabelText("快速选择公开配置"), {
      target: { value: "deepseek-v4-flash" },
    });
    expect(screen.getByLabelText("Provider 名称")).toHaveValue("deepseek");
    expect(screen.getByLabelText("HTTPS Base URL")).toHaveValue(
      "https://api.deepseek.com",
    );
    expect(screen.getByLabelText("模型 ID")).toHaveValue("deepseek-v4-flash");
  });
});
