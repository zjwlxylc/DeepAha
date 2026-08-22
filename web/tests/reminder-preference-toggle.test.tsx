import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ReminderPreferenceToggle from "../components/reminder-preference-toggle";

vi.mock("../app/reminder-actions", () => ({ toggleDeadlineReminderAction: vi.fn() }));

describe("deadline reminder preference", () => {
  it("shows the independent disabled default and fixed delivery semantics", () => {
    render(<ReminderPreferenceToggle preference={null} />);

    expect(screen.getByText("收藏不等于开启提醒")).toBeVisible();
    expect(screen.getByText(/尽快（精确版本通过治理后）/)).toBeVisible();
    expect(screen.getByText(/站内测试收件箱/)).toBeVisible();
    expect(screen.getByLabelText("开启截止日期变化提醒")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "保存提醒设置" })).toBeVisible();
  });

  it("renders enabled state with an associated keyboard-operable control", () => {
    render(
      <ReminderPreferenceToggle
        preference={{
          enabled: true,
          cadence: "AS_SOON_AS_GOVERNED",
          target: "TEST_INBOX",
        }}
      />,
    );

    expect(screen.getByLabelText("开启截止日期变化提醒")).toBeChecked();
    expect(screen.getByRole("button", { name: "保存提醒设置" })).toBeVisible();
  });
});
