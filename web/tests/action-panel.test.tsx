import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ActionPanel from "../components/action-panel";
import type { PersonalActionSnapshot } from "../lib/personal-opportunities";
import { personalDetail, publicId } from "./personal-fixtures";

function actionSnapshot(
  version: number,
  state: PersonalActionSnapshot["state"],
): PersonalActionSnapshot {
  return {
    action_snapshot_id: `019b0000-0000-7000-8000-${900 + version}`.padEnd(36, "0"),
    action_id: "019b0000-0000-7000-8000-000000000901",
    version,
    opportunity_id: personalDetail.eligibility.opportunity_id,
    opportunity_version: 1,
    saved: true,
    state,
    material_items: [],
    last_event_id: `019b0000-0000-7000-8000-${910 + version}`.padEnd(36, "0"),
    input_sha256: "9".repeat(64),
    created_at: "2026-08-22T09:00:00Z",
  };
}

describe("personal action panel", () => {
  it("resets form controls to the latest server action snapshot", () => {
    const { rerender } = render(<ActionPanel publicId={publicId} action={null} />);
    const status = screen.getByRole("combobox", { name: "行动状态" });
    const material = screen.getByRole("textbox", { name: "新增材料项" });
    fireEvent.change(status, { target: { value: "APPLIED" } });
    fireEvent.change(material, { target: { value: "未提交的旧输入" } });

    rerender(
      <ActionPanel publicId={publicId} action={actionSnapshot(2, "PREPARING")} />,
    );

    expect(screen.getByRole("combobox", { name: "行动状态" })).toHaveValue("PREPARING");
    expect(screen.getByRole("textbox", { name: "新增材料项" })).toHaveValue("");
  });
});
