import { describe, expect, it } from "vitest";
import { factAnswer, readableValue, reviewHref, selectedPositions } from "../lib/guided-review";
import { task } from "./investigations-fixture";

describe("guided human review", () => {
  it("never selects or approves on the user's behalf", () => {
    expect(selectedPositions(task, [])).toEqual([]);
    expect(selectedPositions(task, ["unit-1", "made-up"])).toEqual([]);
    expect(factAnswer("", "", false)).toBeNull();
    expect(factAnswer("yes", "", false)).toBeNull();
    expect(factAnswer("unexpected", "clear", false)).toBeNull();
    expect(factAnswer("yes", "clear", false)?.decision).toBe("APPROVE");
    expect(factAnswer("yes", "uncertain", false)?.decision).toBe("NEEDS_ADJUDICATION");
    expect(factAnswer("yes", "clear", true)?.decision).toBe("UNKNOWN");
  });
  it("preserves two selected positions in deep links and avoids JSON for familiar values", () => {
    expect(reviewHref(task.task_id, ["a", "b"], "b", "facts", 3)).toContain("position=a&position=b");
    expect(readableValue({ minimum_level: "MASTER" })).toContain("硕士");
    expect(readableValue({ minimum_level: "MASTER" })).not.toContain("minimum_level");
  });
});
