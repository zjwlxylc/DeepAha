# SG3 Lifecycle & Currentness Implementation Plan

> **For agentic workers:** execute task-by-task with RED→GREEN discipline. SG1/SG2 contracts are frozen.

**Goal:** Keep each actionable opportunity current across corrections, extensions, withdrawals, attachment replacements, partial returns, and targeted rechecks without contaminating sibling units or silently reviving stale dates.

**Architecture:** Reuse SG1 `OpportunityUnit` and versioned `CatalogTarget` rows as the durable target history. Add a pure currentness comparison layer that projects a new WMA revision against the currently approved target frontier before approval, records change metadata inside the pending revision, marks only affected current targets `UPDATE_PENDING`, and cancels only unsafe target reminders. Approval materializes a new target version or explicit withdrawal; missing children remain pending, never auto-withdrawn. History/compare APIs read existing target versions plus the pending change metadata; targeted recheck reuses Direct WMA `RECHECK` tasks.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite/PostgreSQL-compatible models, existing immutable object store, plain product JS UI.

**Spec:** `docs/development/DeepAha_终极目标与分阶段开发规划_v1.0/05_SUBGOAL_ROADMAP.md` SG3 + Gate C semantics; SG1/SG2 accepted baseline.

## Global Constraints

- SG1 actionable target identity and SG2 multi-type contracts must not change.
- One WMA return still receives one overall APPROVE/REJECT decision.
- A missing child in a later return is not evidence of withdrawal.
- Explicit withdrawal requires an explicit lifecycle marker in the accepted return or a reviewer withdrawal action.
- Pending source change may invalidate use of an affected value before the new revision is accepted; rejection must not silently reactivate a stale deadline.
- Sibling units remain CURRENT when their projected content/evidence is unchanged.
- No Eligibility/Ranking/SG4 work.
- No remote WMA call in GET/read paths.
- All historical target/publication/revision rows remain traceable.

---

### Task 1: Freeze SG3 change semantics with failing tests

**Files:**
- Create: `backend/tests/product/test_currentness.py`

Cover RED cases:
1. one POSITION deadline correction marks only that target `UPDATE_PENDING`, leaves sibling CURRENT, cancels only corrected target deadline reminder;
2. common/root field correction affects all descendants;
3. missing child becomes `MISSING_PENDING`, not WITHDRAWN;
4. explicit child withdrawal becomes WITHDRAWN only after APPROVE;
5. attachment hash replacement invalidates only targets whose evidence references that artifact;
6. approved correction creates historical target version and exposes before/after compare;
7. rejected pending correction does not restore stale deadline/reminder;
8. targeted recheck creates one `RECHECK` task scoped to the target/affected fields;
9. source periodic check creates RECHECK/currentness task, not a blind first-investigation instruction.

### Task 2: Add lifecycle markers to the WMA display projection

**Files:**
- Modify: `backend/src/deepaha/product/adapter.py`
- Modify: `backend/src/deepaha/product/granularity.py`

**Interfaces:**
- Normalize explicit lifecycle markers to `ACTIVE | WITHDRAWN` only.
- Carry `lifecycle_status` on root item and child/unit nodes.
- Do not infer withdrawal from absence, status UNKNOWN, or unread material.

### Task 3: Implement pure unit-level currentness comparison

**Files:**
- Create: `backend/src/deepaha/product/currentness.py`
- Modify: `backend/src/deepaha/product/catalog_projection.py`

**Interfaces:**
- `project_candidate_targets(session, opportunity, item, package_notes) -> list[CandidateTarget]`
- `analyze_changes(session, opportunity, current_publication, old_revision, new_revision_content, item, package_notes) -> dict`
- `apply_pending_currentness(session, opportunity, change_summary, pending_revision_id) -> list[str]`

Comparison keys use SG1 stable unit identity; weak identities do not similarity-merge. Diffs distinguish deadline, field/scope, metadata, evidence-artifact replacement, added, missing, explicit withdrawal.

### Task 4: Make intake invalidation precise

**Files:**
- Modify: `backend/src/deepaha/product/intake.py`

At ingest:
- attach per-opportunity `currentness` summary to pending Revision content;
- mark only affected existing targets UPDATE_PENDING;
- preserve old stored values while adding currentness metadata;
- hide/cancel only unsafe deadline usage;
- create target-scoped change notices only for users who saved affected targets;
- leave unchanged sibling targets CURRENT.

At reject:
- retain stale/pending state for genuinely changed target values; do not revive cancelled deadline reminders.

### Task 5: Apply accepted corrections/withdrawals and keep version history

**Files:**
- Modify: `backend/src/deepaha/product/catalog_projection.py`
- Modify: `backend/src/deepaha/product/intake.py`

On APPROVE:
- matching active targets create new CURRENT CatalogTarget versions and supersede prior versions;
- explicitly withdrawn targets transition to WITHDRAWN and get no replacement CURRENT row;
- missing/unprocessed targets remain UPDATE_PENDING;
- root explicit withdrawal withdraws all targets and preserves an accepted withdrawal publication in history;
- change notifications use accepted before/after semantics.

### Task 6: Expose currentness/history/compare and targeted recheck APIs

**Files:**
- Modify: `backend/src/deepaha/product/catalog.py`
- Modify: `backend/src/deepaha/product/tasks.py`
- Modify: `backend/src/deepaha/product/api.py`

Add:
- `GET /api/catalog/{id}/history`
- `GET /api/catalog/{id}/compare?from_id=...&to_id=...`
- `POST /api/manage/catalog/{id}/recheck`

History is bounded, target-scoped, and contains no internal secrets. Recheck requires operator permission and freezes a target/field-specific instruction into the existing Direct WMA task.

### Task 7: Update desktop review/admin and mobile currentness UX

**Files:**
- Modify: `web/public/product/core.js`
- Modify: `web/public/product/user.js`
- Modify: `web/public/product/workbench.js`
- Modify: `web/public/product/product.css`
- Modify: `web/scripts/check-product.mjs`

Behavior:
- pending revision preview shows added/changed/missing/withdrawn target counts and readable affected target rows;
- catalog card uses `UPDATE_PENDING` without erasing unaffected values;
- affected deadline is shown as unavailable/currentness warning;
- detail page shows “有更新待收录” and compact current/history list;
- workbench can create targeted recheck for an affected target when operator role is present;
- no explanatory engineering copy appears in the normal user product.

### Task 8: Real regression, fixtures, docs, and packaging

**Files:**
- Create: `examples/sg3-currentness/` correction/extension/withdrawal/attachment-replacement fixtures
- Create: `docs/sg3/SG3_ACCEPTANCE.md`
- Create: `docs/sg3/SG3_LOCAL_REPRODUCTION.md`
- Update: `README.md`, changelog/version strings

Verify:
- all SG3 tests green;
- SG1 real 106-position database still returns 106 targets after no-op currentness upgrade;
- SG2 five-type fixtures still render correctly;
- at least one correction fixture changes exactly one target and leaves a sibling unchanged;
- browser/API walkthrough shows pending diff, approval, history, new value, cancelled old reminder;
- source/object hashes and old authoritative rows are unchanged except additive/current projection state required by SG3.
