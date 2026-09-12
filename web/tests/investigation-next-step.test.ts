import { describe, expect, it } from "vitest";

import { investigationNextSteps, type InvestigationNextStep } from "../lib/investigation-next-step";
import type { InvestigationTask } from "../lib/investigations";
import { task as base, preparedDocuments, ruleReadyTask, unitSnapshotFixture } from "./investigations-fixture";

const ALL_KEYS = ["dispatch", "materials", "documents", "bindings", "facts", "cross-level", "scope-preflight"];

function stepFor(task: InvestigationTask, key: string): InvestigationNextStep {
  const found = investigationNextSteps(task).find((current) => current.key === key);
  if (!found) throw new Error(`missing next step ${key}`);
  return found;
}

describe("investigationNextSteps", () => {
  it("returns all steps in order for any task", () => {
    expect(investigationNextSteps(base).map((current) => current.key)).toEqual(ALL_KEYS);
  });

  it("maps an in-progress task to explicit next steps and honest reasons", () => {
    expect(stepFor(base, "dispatch")).toMatchObject({ status: "DONE" });
    expect(stepFor(base, "dispatch").reason).toMatch(/不在可发起状态/);
    expect(stepFor(base, "materials").status).toBe("DONE");
    expect(stepFor(base, "materials").reason).toMatch(/已回收 1 份原件/);
    expect(stepFor(base, "documents").status).toBe("ACTIONABLE");
    expect(stepFor(base, "documents").reason).toBeNull();
    expect(stepFor(base, "bindings").status).toBe("WAITING");
    expect(stepFor(base, "bindings").reason).toMatch(/需先完成文档准备/);
    expect(stepFor(base, "facts").status).toBe("WAITING");
    expect(stepFor(base, "facts").reason).toMatch(/身份\/岗位绑定/);
    expect(stepFor(base, "cross-level").status).toBe("WAITING");
    expect(stepFor(base, "cross-level").reason).toMatch(/尚无已整理的规则条件/);
    expect(stepFor(base, "scope-preflight").status).toBe("WAITING");
    expect(stepFor(base, "scope-preflight").reason).toMatch(/条件快照/);
  });

  it("makes dispatch the actionable step for a queued task without delivered material", () => {
    const queued: InvestigationTask = { ...base, status: "QUEUED", delivery_hash: null, materials: [], document_preparation: null, entity_binding: null };
    expect(stepFor(queued, "dispatch").status).toBe("ACTIONABLE");
    expect(stepFor(queued, "dispatch").reason).toBeNull();
    expect(stepFor(queued, "materials").status).toBe("WAITING");
    expect(stepFor(queued, "materials").reason).toMatch(/尚未回收原件/);
    expect(stepFor(queued, "documents").status).toBe("WAITING");
    expect(stepFor(queued, "documents").reason).toMatch(/尚无材料版本/);
  });

  it("keeps dispatch waiting until a persisted intent actually executes", () => {
    const queued: InvestigationTask = { ...base, status: "QUEUED", dispatch_requested_at: "2026-09-11T02:00:00Z" };
    expect(stepFor(queued, "dispatch").status).toBe("WAITING");
    expect(stepFor(queued, "dispatch").reason).toMatch(/已发起/);
  });

  it("advances completed steps and opens cross-level once rules are prepared", () => {
    const ready: InvestigationTask = { ...ruleReadyTask(), document_preparation: preparedDocuments };
    expect(stepFor(ready, "documents").status).toBe("DONE");
    expect(stepFor(ready, "bindings").status).toBe("DONE");
    expect(stepFor(ready, "facts").status).toBe("DONE");
    expect(stepFor(ready, "cross-level").status).toBe("ACTIONABLE");
    // Candidates are still unresolved, so no condition snapshot entry exists yet.
    expect(stepFor(ready, "scope-preflight").status).toBe("WAITING");
    expect(stepFor(ready, "scope-preflight").reason).toMatch(/条件快照/);
  });

  it("opens scope preflight only once a condition snapshot entry exists", () => {
    const { task: snapshotTask } = unitSnapshotFixture();
    const ready: InvestigationTask = { ...snapshotTask, document_preparation: preparedDocuments };
    expect(stepFor(ready, "scope-preflight").status).toBe("ACTIONABLE");
    expect(stepFor(ready, "scope-preflight").reason).toBeNull();
  });

  it("does not label a failed investigation as completed", () => {
    const failed: InvestigationTask = { ...base, status: "FAILED_VALIDATION" };
    expect(stepFor(failed, "dispatch").status).toBe("BLOCKED");
  });

  it("never leaves a non-actionable step unexplained and never embeds an internal id", () => {
    const samples: InvestigationTask[] = [
      base,
      { ...base, status: "QUEUED", delivery_hash: null, materials: [] },
      ruleReadyTask(),
      { ...unitSnapshotFixture().task, document_preparation: preparedDocuments },
    ];
    for (const sample of samples) {
      for (const current of investigationNextSteps(sample)) {
        if (current.status === "ACTIONABLE") {
          expect(current.reason).toBeNull();
        } else {
          expect(current.reason?.trim()).toBeTruthy();
        }
        expect(current.anchor.startsWith("#")).toBe(true);
        if (current.href) expect(current.href).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}/i);
      }
    }
  });
});
