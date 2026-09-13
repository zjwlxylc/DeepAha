import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import GuidedSelection from "../components/investigations/guided-selection";
import GuidedFact from "../components/investigations/guided-fact";
import GuidedRule from "../components/investigations/guided-rule";
import { task, ruleReadyTask } from "./investigations-fixture";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

describe("guided review plain-language interaction", () => {
  it("shows a single continue action only after selecting two real positions", () => {
    const t = structuredClone(task);
    t.binding_entities!.push({ id: "position-2", name: "第二岗位", kind: "position", code: "P002" });
    render(<GuidedSelection task={t} />);
    expect(screen.getByRole("button", { name: "选满两个岗位后继续" })).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /教学岗位/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /第二岗位/ }));
    expect(screen.getByRole("link", { name: "继续：核对这两个岗位" })).toHaveAttribute("href", expect.stringContaining("position=position-1&position=position-2"));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "没有此岗位" } });
    expect(screen.getByText("已选 2 / 2 个")).toBeVisible();
  });
  it("requires both support and scope answers, and resetting clears the earlier approval", () => {
    render(<GuidedFact task={ruleReadyTask()} requestKey="request" next="/next" />);
    expect(screen.queryByRole("button", { name: "保存我的判断" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "是，原文支持这条内容" }));
    expect(screen.queryByRole("button", { name: "保存我的判断" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "已核对岗位、共同条件及更正，没有未解决冲突" }));
    expect(screen.getByRole("button", { name: "保存我的判断" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "重新回答" }));
    fireEvent.click(screen.getByRole("radio", { name: "是，原文支持这条内容" }));
    expect(screen.queryByRole("button", { name: "保存我的判断" })).not.toBeInTheDocument();
  });
  it("lets a person defer a rule without inventing its effective time", () => {
    render(<GuidedRule task={ruleReadyTask()} requestKey="request" next="/next" />);
    expect(screen.getByText("证据问题 1 / 4")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "我现在无法判断" }));
    fireEvent.click(screen.getByRole("radio", { name: "生效时间只有日期，或没有说明" }));
    expect(screen.getByRole("button", { name: "保存我的判断" })).toBeEnabled();
    expect(document.querySelector('input[name="decision"]')).toHaveValue("NEEDS_ADJUDICATION");
    expect(document.querySelector('input[name^="effective_at:"]')).toHaveValue("");
  });
  it("does not misdescribe parser uncertainty as absence of an official requirement", () => {
    const t = ruleReadyTask();
    t.fact_review!.current!.rows[0].abstained = true;
    t.fact_review!.current!.rows[0].normalized_value_candidate = null;
    t.fact_review!.current!.rows[0].issue_codes = ["UNKNOWN_NORMALIZATION_UNSUPPORTED"];
    render(<GuidedFact task={t} requestKey="request" next="/next" />);
    expect(screen.getByText("暂不能形成可靠解释，请结合原文核对")).toBeVisible();
    expect(screen.queryByText("原文没有明确说明，保留未知")).not.toBeInTheDocument();
  });
});
