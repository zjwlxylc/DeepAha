import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import InvestigationEvidence from "../components/investigations/evidence";
import { task } from "./investigations-fixture";

it("keeps each original quote with its own condition when paging and searching a large delivery", () => {
  const facts = Array.from({ length: 27 }, (_, index) => ({ ...task.facts[0],
    field: `条件 ${index}`, value: `要求 ${index}`, note: null,
    evidence: [{ ...task.facts[0].evidence[0], quote: `原文第 ${index} 项` }],
  }));
  render(<InvestigationEvidence task={{ ...task, facts }} />);
  const browser = screen.getByRole("group", { name: "原文对照" });
  expect(within(browser).getAllByRole("article")).toHaveLength(12);
  expect(screen.queryByText("原文第 26 项")).not.toBeInTheDocument();
  fireEvent.change(within(browser).getByRole("searchbox"), { target: { value: "要求 26" } });
  const card = within(browser).getByRole("article");
  expect(within(card).getByText("条件 26")).toBeVisible();
  expect(within(card).getByText("原文第 26 项")).toBeVisible();
  expect(within(card).getByRole("link", { name: /下载原件/ })).toHaveAttribute("href", `/review/investigations/${task.task_id}/materials/attachment-1`);
  expect(screen.queryByRole("button", { name: /批准/ })).not.toBeInTheDocument();
});
