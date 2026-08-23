import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PersonalOpportunityPage from "../app/me/opportunities/[publicId]/page";
import EligibilityExplanation from "../components/eligibility-explanation";
import {
  getPersonalOpportunity,
  type EligibilityStatus,
} from "../lib/personal-opportunities";
import {
  personalDetail,
  publicId,
  ruleSetUnavailableDetail,
} from "./personal-fixtures";

vi.mock("../lib/personal-opportunities", async () => {
  const actual = await vi.importActual<typeof import("../lib/personal-opportunities")>(
    "../lib/personal-opportunities",
  );
  return { ...actual, getPersonalOpportunity: vi.fn() };
});

const mockedDetail = vi.mocked(getPersonalOpportunity);

describe("personal opportunity detail", () => {
  beforeEach(() => {
    mockedDetail.mockReset();
    mockedDetail.mockResolvedValue(personalDetail);
  });

  it("explains uncertainty, evidence, urgency and official next action", async () => {
    render(
      await PersonalOpportunityPage({ params: Promise.resolve({ publicId }) }),
    );

    expect(screen.getByRole("heading", { level: 1, name: personalDetail.opportunity.title })).toBeVisible();
    expect(screen.getByRole("heading", { name: "仍需确认" })).toBeVisible();
    expect(screen.getByText(/缺少：户籍地区/)).toBeVisible();
    expect(screen.getByText(/2026-09-20/)).toBeVisible();
    expect(screen.getByRole("link", { name: "查看官方证据" })).toHaveAttribute(
      "href",
      personalDetail.opportunity.key_evidence[0].official_url,
    );
    expect(screen.getByRole("button", { name: "记录并打开官方入口" })).toBeVisible();
    expect(screen.getByRole("link", { name: "纠正这条判断" })).toHaveAttribute(
      "href",
      `/me/opportunities/${publicId}/feedback`,
    );
    expect(document.body.textContent).not.toMatch(/匹配度|置信度|\d+%/);
  });

  it.each<[EligibilityStatus, string]>([
    ["ELIGIBLE", "符合条件"],
    ["LIKELY_ELIGIBLE", "大概率符合"],
    ["UNCERTAIN", "仍需确认"],
    ["INELIGIBLE", "当前不符合"],
  ])("maps %s to an explicit four-state label", (status, label) => {
    render(
      <EligibilityExplanation
        eligibility={{
          ...personalDetail.eligibility,
          eligibility_result: {
            ...personalDetail.eligibility.eligibility_result,
            status,
          },
        }}
        evidence={personalDetail.opportunity.key_evidence}
      />,
    );

    expect(screen.getByRole("heading", { name: label })).toBeVisible();
  });

  it("renders one EvidenceRef supporting multiple fields without duplicate React keys", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const evidence = personalDetail.opportunity.key_evidence[0];

    render(
      <EligibilityExplanation
        eligibility={personalDetail.eligibility}
        evidence={[evidence, { ...evidence, field_path: "application_window.closes_on" }]}
      />,
    );

    expect(consoleError.mock.calls.flat().join(" ")).not.toMatch(/same key|unique key/i);
    consoleError.mockRestore();
  });

  it("shows governed uncertainty when the current opportunity has no exact approved rules", async () => {
    mockedDetail.mockResolvedValue(ruleSetUnavailableDetail);

    render(
      await PersonalOpportunityPage({ params: Promise.resolve({ publicId }) }),
    );

    expect(screen.getByRole("heading", { name: "仍需确认" })).toBeVisible();
    expect(screen.getByText(/当前机会版本尚无已批准的精确规则集/)).toBeVisible();
    expect(screen.getByRole("link", { name: "查看官方证据" })).toHaveAttribute(
      "href",
      ruleSetUnavailableDetail.opportunity.key_evidence[0].official_url,
    );
    expect(screen.queryByRole("link", { name: "纠正这条判断" })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/匹配度|置信度|\d+%/);
  });
});
