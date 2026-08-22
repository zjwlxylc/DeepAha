import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ProfileForm from "../components/profile-form";


describe("progressive profile form", () => {
  it("labels optional fields, supports skip and states the privacy boundary", () => {
    render(<ProfileForm initialState={null} action={vi.fn()} />);

    expect(screen.getByText(/只收集当前资格与行动所需信息/)).toBeVisible();
    expect(screen.getByLabelText("专业名称（可跳过）")).toBeVisible();
    const skip = screen.getByRole("checkbox", { name: "暂时跳过专业信息" });
    fireEvent.click(skip);
    expect(screen.queryByLabelText("专业名称（可跳过）")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存画像并重新判断" })).toBeVisible();
  });
});
