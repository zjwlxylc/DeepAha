import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ReminderPage from "../app/me/reminders/page";
import ReminderInboxCard from "../components/reminder-inbox-card";
import { getDeadlineReminderPreference, getReminderInbox } from "../lib/reminders";

vi.mock("../lib/reminders", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/reminders")>();
  return {
    ...original,
    getDeadlineReminderPreference: vi.fn(),
    getReminderInbox: vi.fn(),
  };
});
vi.mock("../app/reminder-actions", () => ({ toggleDeadlineReminderAction: vi.fn() }));

const entry = {
  inbox_entry_id: "019b0000-0000-7000-8000-000000000821",
  reminder_id: "019b0000-0000-7000-8000-000000000822",
  user_id: "019b0000-0000-7000-8000-000000000831",
  opportunity_id: "019b0000-0000-7000-8000-000000000823",
  opportunity_public_id: "opp_019b0000000070008000000000000823",
  opportunity_title: "合成国企校园招聘项目",
  event_id: "019b0000-0000-7000-8000-000000000824",
  from_version: 6,
  to_version: 7,
  old_closes_on: "2026-09-20",
  new_closes_on: "2026-09-30",
  direction: "EXTENDED" as const,
  previous_evidence_ref_id: "019b0000-0000-7000-8000-000000000825",
  current_evidence_ref_id: "019b0000-0000-7000-8000-000000000826",
  previous_official_url: "https://official.example.test/v6",
  current_official_url: "https://official.example.test/v7",
  personal_detail_path: "/me/opportunities/opp_019b0000000070008000000000000823",
  detected_at: "2026-08-22T09:05:00Z",
  delivered_at: "2026-08-22T12:00:00Z",
  target: "TEST_INBOX" as const,
  contract_version: "0.7.0" as const,
};

const mockedPreference = vi.mocked(getDeadlineReminderPreference);
const mockedInbox = vi.mocked(getReminderInbox);

const enabledPreference = {
  preference_snapshot_id: "019b0000-0000-7000-8000-000000000841",
  preference_id: "019b0000-0000-7000-8000-000000000842",
  user_id: entry.user_id,
  version: 1,
  predecessor_snapshot_id: null,
  reminder_kind: "DEADLINE_CHANGED" as const,
  enabled: true,
  cadence: "AS_SOON_AS_GOVERNED" as const,
  target: "TEST_INBOX" as const,
  actor_user_id: entry.user_id,
  preference_policy_version: "phase8-deadline-reminder-v1" as const,
  contract_version: "0.7.0" as const,
  created_at: "2026-08-22T12:00:00Z",
};

describe("test reminder inbox", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedPreference.mockResolvedValue(null);
    mockedInbox.mockResolvedValue({ items: [], count: 0 });
  });

  it("renders exact old/new dates, direction, evidence and personal action link", () => {
    render(<ReminderInboxCard entry={entry} />);

    expect(screen.getByRole("heading", { name: entry.opportunity_title })).toBeVisible();
    expect(screen.getByText("延后")).toBeVisible();
    expect(screen.getByText("2026-09-20")).toBeVisible();
    expect(screen.getByText("2026-09-30")).toBeVisible();
    expect(screen.getByText(/2026年8月22日/)).toBeVisible();
    expect(screen.getByRole("link", { name: "查看变更前官方证据" })).toHaveAttribute(
      "href",
      entry.previous_official_url,
    );
    expect(screen.getByRole("link", { name: "查看当前官方证据" })).toHaveAttribute(
      "href",
      entry.current_official_url,
    );
    expect(screen.getByRole("link", { name: "回到个人行动" })).toHaveAttribute(
      "href",
      entry.personal_detail_path,
    );
  });

  it("shows the disabled and empty test-only state", async () => {
    render(await ReminderPage());

    expect(
      screen.getByRole("heading", { level: 1, name: /截止变化提醒测试收件箱/ }),
    ).toBeVisible();
    expect(screen.getByText(/当前未开启截止日期变化提醒/)).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("测试收件箱还是空的");
    expect(screen.getByText(/固定合成许可安全夹具/)).toBeVisible();
  });

  it("renders one populated immutable reminder without human metric claims", async () => {
    mockedPreference.mockResolvedValue(enabledPreference);
    mockedInbox.mockResolvedValue({ items: [entry], count: 1 });

    render(await ReminderPage());

    expect(screen.getByRole("heading", { name: entry.opportunity_title })).toBeVisible();
    expect(document.body.textContent).not.toMatch(/打开率|投诉率|留存率|行动率|真实推送/);
  });
});
