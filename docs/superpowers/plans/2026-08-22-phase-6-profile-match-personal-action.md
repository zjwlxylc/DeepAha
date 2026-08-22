# DeepAha Phase 6 Profile, Match and Personal Action Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user explicitly requested
> continuous inline execution in this isolated worktree; do not dispatch subagents.

**Goal:** Build an authenticated, user-isolated Phase 6 vertical slice from progressive UserState to
reproducible v0.4 eligibility, separate deterministic priority ranking and idempotent personal action.

**Architecture:** Add v0.5 UserState/ranking/action contracts while keeping v0.1-v0.4 bytes and
imports unchanged. Persist an immutable owner-scoped UserState linked to a non-synthetic v0.4 profile
projection, use the existing RuleSet/compiler/Eligibility Engine/MatchSnapshot for hard eligibility,
and persist ranking and actions separately behind `/api/v1/me` authenticated-principal routes.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL 18, pytest,
Next.js 16/React 19/TypeScript, Vitest/Testing Library, Playwright/Chromium, Docker Compose, GitHub
Actions.

**Spec:** `docs/superpowers/specs/2026-08-22-phase-6-profile-match-personal-action-design.md`

## Global Constraints

- Exact upstream is `8d9b36c96174bffb303e7f981bd1775ebd8fa672`; do not rebase, force-push,
  rewrite or merge Phase 5.
- Keep Phase 5 PR #5 open/draft/unmerged and stack the Phase 6 draft PR on
  `codex/phase-5-public-trust-layer`.
- Never access, connect to, modify, stop, reuse or occupy Phase 2/3/4/5 ports `55432`-`55435` or
  `55000`-`55003`; Phase 6 uses only `55436`, `55004` and `deepaha-phase6-*`.
- Keep every v0.1-v0.4 Schema byte and Python import path unchanged.
- Missing or skipped facts remain unknown. `INELIGIBLE` still requires deterministic official
  evidence. Ranking never changes eligibility.
- Never emit a matching percentage, probability, model confidence or LLM-derived hard conclusion.
- Collect no name, email, phone, government ID or free-form biography.
- All writes are idempotent, owner-scoped and audited. No public `user_id` is accepted.
- Use only fixed, permission-safe, synthetic fixtures marked non-business-truth and
  non-Release-Qualification evidence.
- Do not implement Phase 7 feedback/review or Phase 8 reminders/notifications.
- Use `apply_patch` for edits, exact-path `git add`, independent commits and ordinary push only.
- Startup axes remain Implementation `NOT_STARTED`, Engineering Gate `OPEN`, Release Qualification
  `NOT_STARTED`, Contract Maturity `PROPOSED` until evidence supports a later state.

## File map

| Area | Files and responsibility |
|---|---|
| v0.5 contract | `backend/src/deepaha/contracts/phase6.py`, `contracts/schemas/v0.5.0/*.json`, `contracts/examples/v0.5.0/phase-6-example.json` |
| contract export | `backend/src/deepaha/contracts/export.py`, `backend/src/deepaha/contracts/__init__.py` |
| persistence | `backend/src/deepaha/personal/models.py`, `backend/migrations/versions/20260822_0006_phase6_personal_action.py`, `backend/src/deepaha/db/models.py` |
| identity | `backend/src/deepaha/personal/auth.py`, `backend/src/deepaha/core/settings.py`, `backend/src/deepaha/db/session.py` |
| profile | `backend/src/deepaha/personal/profile.py`, `backend/src/deepaha/personal/schemas.py` |
| match/rank | `backend/src/deepaha/personal/matching.py`, narrow extension to `backend/src/deepaha/eligibility/service.py` |
| actions/API | `backend/src/deepaha/personal/actions.py`, `backend/src/deepaha/api/personal.py`, `backend/src/deepaha/main.py` |
| Web/PWA | `web/lib/personal-opportunities.ts`, `web/app/personal-actions.ts`, profile/personal routes, shared personal components, `web/app/globals.css`, `web/components/site-header.tsx` |
| fixtures/tests | `backend/tests/fixtures/personal/*`, `backend/tests/personal/*`, `backend/tests/contracts/test_phase6_contracts.py`, `backend/tests/integration/test_phase6_*.py`, `backend/tests/api/test_personal.py`, `web/tests/personal-*.test.tsx` |
| verification | `infra/compose.phase6.yaml`, `scripts/verify-phase6.ps1`, `.github/workflows/ci.yml`, `backend/tests/test_phase6_verifier_scope.py` |
| evidence | `docs/gates/phase-6/*` |

---

### Task 1: v0.5 immutable contracts and backward compatibility

**Files:**
- Create: `backend/src/deepaha/contracts/phase6.py`
- Create: `backend/tests/contracts/test_phase6_contracts.py`
- Create: `contracts/schemas/v0.5.0/user-state-snapshot.schema.json`
- Create: `contracts/schemas/v0.5.0/personal-ranking-snapshot.schema.json`
- Create: `contracts/schemas/v0.5.0/personal-action-snapshot.schema.json`
- Create: `contracts/schemas/v0.5.0/personal-action-event.schema.json`
- Create: `contracts/examples/v0.5.0/phase-6-example.json`
- Modify: `backend/src/deepaha/contracts/export.py`
- Modify: `backend/src/deepaha/contracts/__init__.py`

**Interfaces:**
- Consumes: `ProfileAttributesSchemaV04`, `EligibilityStatus`, `OpportunityTypeV02`, UUIDv7 common
  types and existing export functions.
- Produces: `UserStateSnapshotSchemaV05`, `PersonalRankingSnapshotSchemaV05`,
  `PersonalRankingItemSchemaV05`, `PersonalActionSnapshotSchemaV05`,
  `PersonalActionEventSchemaV05`, `ActionState`, `ActionEventType`, `LifeStage`, `GoalType`,
  `ProfileFieldV05` and `render_phase6_schemas()` writing directory `v0.5.0`.

- [ ] **Step 1: Write failing contract tests**

```python
def test_user_state_preserves_unknown_and_rejects_skipped_provided_conflict() -> None:
    state = UserStateSnapshotSchemaV05.model_validate(user_state_values())
    assert state.attributes.birth_date is None
    assert "birth_date" in state.skipped_fields
    with pytest.raises(ValidationError, match="skipped"):
        UserStateSnapshotSchemaV05.model_validate(
            user_state_values(attributes=attributes_values(birth_date="2003-01-01"))
        )

def test_ranking_has_no_score_and_at_most_three_items() -> None:
    assert "score" not in PersonalRankingItemSchemaV05.model_fields
    assert "confidence" not in PersonalRankingItemSchemaV05.model_fields
    with pytest.raises(ValidationError, match="at most 3"):
        PersonalRankingSnapshotSchemaV05.model_validate(ranking_values(item_count=4))

def test_prior_schema_bytes_are_unchanged() -> None:
    assert render_phase1_schemas() == committed_schema_bytes("v0.1.0")
    assert render_phase2_schemas() == committed_schema_bytes("v0.2.0")
    assert render_phase3_schemas() == committed_schema_bytes("v0.3.0")
    assert render_phase4_schemas() == committed_schema_bytes("v0.4.0")
```

- [ ] **Step 2: Run the RED contract target**

Run: `cd backend; uv run pytest tests/contracts/test_phase6_contracts.py -q`

Expected: collection fails because `deepaha.contracts.phase6` does not exist.

- [ ] **Step 3: Implement the minimum frozen v0.5 types**

```python
class UserStateSnapshotSchemaV05(ContractModel):
    user_state_snapshot_id: EntityId
    user_state_id: EntityId
    version: VersionNumber
    qualification_profile_snapshot_id: EntityId
    life_stage: LifeStage | None
    goal_types: tuple[GoalType, ...]
    attributes: ProfileAttributesSchemaV04
    preference_regions: tuple[NonEmptyString, ...]
    preference_types: tuple[OpportunityTypeV02, ...]
    skipped_fields: tuple[ProfileFieldV05, ...]
    personalization_enabled: bool
    consent_version: Literal["phase6-consent-v1"]
    allowed_purposes: tuple[Literal["ELIGIBILITY", "PERSONAL_RANKING", "ACTION_TRACKING"], ...]
    scenario_clock: date
    input_sha256: Sha256
    created_at: Instant

class PersonalRankingItemSchemaV05(ContractModel):
    ordinal: int = Field(ge=1, le=3)
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    match_snapshot_id: EntityId
    eligibility_status: EligibilityStatus
    reason_codes: tuple[RankingReasonCode, ...]
    deadline: date
```

Add validators for sorted unique set-like fields, skipped/provided conflicts, exact 90-day window,
consecutive ranks, unique opportunities, no `INELIGIBLE` priority item and action/event consistency.
Extend the exporter with `PHASE6_SCHEMAS`, `render_phase6_schemas()` and CLI choice `0.5.0`; the
function name follows the project phase while the output directory carries the contract version.

- [ ] **Step 4: Export Schemas and add the strict synthetic example**

Run: `cd backend; uv run python -m deepaha.contracts.export .. --version 0.5.0`

The example must contain `synthetic=true`, `business_truth=false`,
`release_qualification_eligible=false`, one unknown optional field and no personal identifiers.

- [ ] **Step 5: Verify contract parity and prior bytes**

Run: `cd backend; uv run pytest tests/contracts/test_phase1_contracts.py tests/contracts/test_phase2_contracts.py tests/contracts/test_phase3_contracts.py tests/contracts/test_phase4_contracts.py tests/contracts/test_phase6_contracts.py -q`

Expected: PASS and the test confirms all committed v0.1-v0.4 bytes still equal their renderers.

- [ ] **Step 6: Commit and push exact files**

```powershell
git add -- backend/src/deepaha/contracts/phase6.py backend/src/deepaha/contracts/export.py backend/src/deepaha/contracts/__init__.py backend/tests/contracts/test_phase6_contracts.py contracts/schemas/v0.5.0 contracts/examples/v0.5.0/phase-6-example.json
git commit -m "feat: define phase 6 personal contracts"
git push
```

### Task 2: Migration, principal boundary and immutable progressive UserState

**Files:**
- Create: `backend/src/deepaha/personal/__init__.py`
- Create: `backend/src/deepaha/personal/models.py`
- Create: `backend/src/deepaha/personal/auth.py`
- Create: `backend/src/deepaha/personal/profile.py`
- Create: `backend/src/deepaha/personal/schemas.py`
- Create: `backend/migrations/versions/20260822_0006_phase6_personal_action.py`
- Create: `backend/tests/personal/__init__.py`
- Create: `backend/tests/personal/test_auth.py`
- Create: `backend/tests/personal/test_profile.py`
- Create: `backend/tests/integration/test_phase6_profile_persistence.py`
- Modify: `backend/src/deepaha/core/settings.py`
- Modify: `backend/src/deepaha/db/session.py`
- Modify: `backend/src/deepaha/db/models.py`

**Interfaces:**
- Consumes: v0.5 UserState contract, v0.4 `ProfileSnapshotModel`, SQLAlchemy session factory.
- Produces: `Principal(user_id: UUID)`, `resolve_principal(authorization, session, settings)`,
  `get_personal_session()`, `ProfileService.save(principal, command)`, and
  `ProfileService.get_current(principal)`.

- [ ] **Step 1: Write authorization and profile RED tests**

```python
def test_auth_uses_digest_and_fails_closed() -> None:
    assert token_digest("fixture-session-a") == sha256(b"fixture-session-a").hexdigest()
    with pytest.raises(AuthenticationError):
        resolve_principal("Bearer fixture-session-a", session, Settings(environment="production"))

def test_profile_save_versions_and_identical_request_reuses_snapshot() -> None:
    first = service.save(USER_A, profile_command(), idempotency_key="profile-request-0001")
    replay = service.save(USER_A, profile_command(), idempotency_key="profile-request-0001")
    changed = service.save(
        USER_A,
        profile_command(preference_regions=("合成宁波市",)),
        idempotency_key="profile-request-0002",
    )
    assert replay.user_state_snapshot_id == first.user_state_snapshot_id
    assert changed.version == first.version + 1
    assert first.attributes.birth_date is None
```

Add negative tests for missing/invalid/expired/revoked tokens, caller-supplied extra `user_id`,
optional skips, cross-user reads and absence of tokens/sensitive fields in errors/log records.

- [ ] **Step 2: Run RED targets**

Run: `cd backend; uv run pytest tests/personal/test_auth.py tests/personal/test_profile.py -q`

Expected: collection fails because `deepaha.personal` does not exist.

- [ ] **Step 3: Implement principal and writable transaction dependency**

```python
@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID

def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()

def get_personal_session() -> Generator[Session]:
    engine = get_engine()
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            engine.dispose()
```

`resolve_principal` requires `personal_auth_mode="fixture"` and environment `development` or `test`,
parses exactly one bearer token, compares its digest server-side and checks active user,
`expires_at > now`, and `revoked_at is None`.

- [ ] **Step 4: Implement migration and ORM constraints**

Create the seven tables from the design. Replace the named
`ck_profile_snapshots_synthetic_only` check with `synthetic in (true, false)` without modifying
existing rows. Add composite owner/version uniqueness, JSON type checks, token/hash format checks,
restrictive foreign keys and downgrade refusal when personal or non-synthetic rows exist.

- [ ] **Step 5: Implement immutable ProfileService**

```python
class ProfileService:
    def get_current(self, principal: Principal) -> UserStateSnapshotSchemaV05 | None: ...

    def save(
        self,
        principal: Principal,
        command: ProfileWrite,
        *,
        idempotency_key: str,
    ) -> UserStateSnapshotSchemaV05: ...
```

Canonicalize the request, hash it with owner and operation, reuse an identical idempotency record,
create a non-synthetic v0.4 qualification projection and immutable UserState in one transaction,
and never infer values for skipped fields.

- [ ] **Step 6: Run unit and migration integration tests**

Run: `cd backend; uv run pytest tests/personal/test_auth.py tests/personal/test_profile.py -q`

Run in Phase 6 disposable PostgreSQL only:
`cd backend; uv run pytest -m integration tests/integration/test_phase6_profile_persistence.py tests/integration/test_migrations.py -q`

Expected: PASS; migration downgrade refuses with Phase 6 rows and succeeds only when empty.

- [ ] **Step 7: Commit and push exact files**

```powershell
git add -- backend/src/deepaha/personal backend/src/deepaha/core/settings.py backend/src/deepaha/db/session.py backend/src/deepaha/db/models.py backend/migrations/versions/20260822_0006_phase6_personal_action.py backend/tests/personal backend/tests/integration/test_phase6_profile_persistence.py backend/tests/integration/test_migrations.py
git commit -m "feat: persist isolated progressive profiles"
git push
```

### Task 3: Owner-aware v0.4 eligibility reuse and deterministic ranking

**Files:**
- Create: `backend/src/deepaha/personal/matching.py`
- Create: `backend/tests/personal/test_matching.py`
- Create: `backend/tests/personal/test_ranking.py`
- Create: `backend/tests/integration/test_phase6_match_replay.py`
- Modify: `backend/src/deepaha/eligibility/service.py`

**Interfaces:**
- Consumes: `ProfileService` current state, Phase 5 public candidates, approved RuleSet,
  `EligibilityService`, `MajorCatalog`, `ApprovedMajorMapping`.
- Produces: `EligibilityService.evaluate_personal_and_save(match_input)`,
  `PersonalMatchService.run(principal)`, `PersonalMatchService.get_detail(principal, public_id)` and
  pure `rank_personal_matches(matches, state, window_end)`.

- [ ] **Step 1: Write failing personal-match and counterfactual tests**

```python
def test_personal_match_binds_exact_versions_and_replays() -> None:
    ranking = service.run(USER_A)
    stored = eligibility_service.replay(ranking.items[0].match_snapshot_id)
    assert stored.opportunity_version == ranking.items[0].opportunity_version
    assert stored.profile_snapshot_id == state.qualification_profile_snapshot_id
    assert stored.scenario_clock == state.scenario_clock

def test_soft_preference_changes_order_not_eligibility() -> None:
    before = service.run(USER_A)
    profile_service.save(USER_A, changed_preferences(), idempotency_key="profile-pref-0002")
    after = service.run(USER_A)
    assert statuses_by_opportunity(before) == statuses_by_opportunity(after)
    assert match_hashes_by_opportunity(before) == match_hashes_by_opportunity(after)
    assert opportunity_order(before) != opportunity_order(after)
```

Add cases for all four states, missing-field downgrade, official conflict protection, no exact
RuleSet, deadline exactly today/+90, deadline +91, closed/cancelled/unknown status and max three.

- [ ] **Step 2: Run RED targets**

Run: `cd backend; uv run pytest tests/personal/test_matching.py tests/personal/test_ranking.py -q`

Expected: fail because `PersonalMatchService` and `evaluate_personal_and_save` are absent.

- [ ] **Step 3: Add a narrow personal entry to EligibilityService**

```python
def evaluate_personal_and_save(self, match_input: MatchInput) -> MatchSnapshotSchemaV04:
    return self._evaluate_and_save(match_input, required_synthetic=False)

def evaluate_and_save(self, match_input: MatchInput) -> MatchSnapshotSchemaV04:
    return self._evaluate_and_save(match_input, required_synthetic=True)
```

Factor only the existing method body and `_load_input` guard; do not change v0.4 output or default
synthetic behavior. Ownership remains enforced by `PersonalMatchService` before this method is called.

- [ ] **Step 4: Implement deterministic candidate selection and ranking**

```python
def rank_personal_matches(
    matches: Sequence[RankableMatch],
    state: UserStateSnapshotSchemaV05,
) -> tuple[PersonalRankingItemSchemaV05, ...]:
    actionable = [item for item in matches if item.status is not EligibilityStatus.INELIGIBLE]
    ordered = sorted(actionable, key=lambda item: item.sort_key(state))
    return tuple(item.to_contract(index + 1) for index, item in enumerate(ordered[:3]))
```

`sort_key` is exactly `(eligibility_band, -region_match, -type_match, deadline, public_id)`, with both
preference matches zero when personalization is disabled. Persist one canonical ranking snapshot
bound to state, window, ranker version and all match hashes.

- [ ] **Step 5: Verify matching and replay**

Run: `cd backend; uv run pytest tests/eligibility tests/personal/test_matching.py tests/personal/test_ranking.py -q`

Run in Phase 6 disposable PostgreSQL only:
`cd backend; uv run pytest -m integration tests/integration/test_phase4_match_replay.py tests/integration/test_phase6_match_replay.py -q`

Expected: PASS; Phase 4 synthetic guard still rejects personal rows through its original method.

- [ ] **Step 6: Commit and push exact files**

```powershell
git add -- backend/src/deepaha/eligibility/service.py backend/src/deepaha/personal/matching.py backend/tests/personal/test_matching.py backend/tests/personal/test_ranking.py backend/tests/integration/test_phase6_match_replay.py
git commit -m "feat: rank reproducible personal matches"
git push
```

### Task 4: Idempotent action services and personal API

**Files:**
- Create: `backend/src/deepaha/personal/actions.py`
- Create: `backend/src/deepaha/api/personal.py`
- Create: `backend/tests/personal/test_actions.py`
- Create: `backend/tests/api/test_personal.py`
- Create: `backend/tests/integration/test_phase6_personal_api.py`
- Modify: `backend/src/deepaha/main.py`

**Interfaces:**
- Consumes: authenticated `Principal`, Profile/Match services, governed Phase 5 detail and Phase 6
  action models.
- Produces: `ActionService.set_saved`, `record_official_link`, `set_material_plan`, `set_status` and
  `/api/v1/me` response models with private/no-store headers.

- [ ] **Step 1: Write failing action and API security tests**

```python
def test_action_writes_are_idempotent_and_audited_once() -> None:
    first = service.set_saved(USER_A, PUBLIC_ID, True, idempotency_key="saved-request-0001")
    replay = service.set_saved(USER_A, PUBLIC_ID, True, idempotency_key="saved-request-0001")
    assert replay == first
    assert count_events(USER_A, "SAVED_CHANGED") == 1

def test_other_user_and_unknown_action_have_identical_response(client) -> None:
    other = client.get(f"/api/v1/me/opportunities/{USER_B_PUBLIC_ID}", headers=USER_A_AUTH)
    unknown = client.get("/api/v1/me/opportunities/opp_00000000000000000000000000000000", headers=USER_A_AUTH)
    assert (other.status_code, other.json()) == (unknown.status_code, unknown.json())
```

Add tests for missing auth, `user_id` extra-field rejection, changed request under reused key ->
`409`, owner isolation, transaction rollback, bounded material labels, official URL provenance,
private/no-store and absence of feedback/reminder/percentage fields.

- [ ] **Step 2: Run RED targets**

Run: `cd backend; uv run pytest tests/personal/test_actions.py tests/api/test_personal.py -q`

Expected: fail because action service and personal router are absent.

- [ ] **Step 3: Implement the action service**

```python
class ActionService:
    def set_saved(self, principal: Principal, public_id: str, saved: bool, *, idempotency_key: str) -> PersonalActionSnapshotSchemaV05: ...
    def record_official_link(self, principal: Principal, public_id: str, *, idempotency_key: str) -> OfficialLinkResult: ...
    def set_material_plan(self, principal: Principal, public_id: str, items: tuple[MaterialItem, ...], *, idempotency_key: str) -> PersonalActionSnapshotSchemaV05: ...
    def set_status(self, principal: Principal, public_id: str, state: ActionState, *, idempotency_key: str) -> PersonalActionSnapshotSchemaV05: ...
```

Use one transaction for snapshot, event and idempotency record. Official-link recording returns only
the current governed Phase 5 application URL and event identity.

- [ ] **Step 4: Implement `/api/v1/me` routes and stable problems**

Use `Depends(require_principal)` and the writable session. Validate exactly one `Idempotency-Key` for
writes. Apply `Cache-Control: private, no-store` to success and problem responses. Keep public routes
unchanged and include the new router in `create_app()`.

- [ ] **Step 5: Verify unit/API/integration behavior**

Run: `cd backend; uv run pytest tests/personal tests/api/test_personal.py -q`

Run in Phase 6 disposable PostgreSQL only:
`cd backend; uv run pytest -m integration tests/integration/test_phase6_personal_api.py -q`

Expected: PASS, including all owner/isolation and negative-shape assertions.

- [ ] **Step 6: Commit and push exact files**

```powershell
git add -- backend/src/deepaha/personal/actions.py backend/src/deepaha/api/personal.py backend/src/deepaha/main.py backend/tests/personal/test_actions.py backend/tests/api/test_personal.py backend/tests/integration/test_phase6_personal_api.py
git commit -m "feat: expose isolated personal action api"
git push
```

### Task 5: Responsive personal Web/PWA flow

**Files:**
- Create: `web/lib/personal-opportunities.ts`
- Create: `web/app/personal-actions.ts`
- Create: `web/components/profile-form.tsx`
- Create: `web/components/eligibility-explanation.tsx`
- Create: `web/components/personal-opportunity-card.tsx`
- Create: `web/components/action-panel.tsx`
- Create: `web/app/profile/page.tsx`
- Create: `web/app/profile/loading.tsx`
- Create: `web/app/profile/error.tsx`
- Create: `web/app/me/opportunities/page.tsx`
- Create: `web/app/me/opportunities/loading.tsx`
- Create: `web/app/me/opportunities/error.tsx`
- Create: `web/app/me/opportunities/[publicId]/page.tsx`
- Create: `web/app/me/opportunities/[publicId]/loading.tsx`
- Create: `web/app/me/opportunities/[publicId]/error.tsx`
- Create: `web/tests/personal-api-client.test.ts`
- Create: `web/tests/profile.test.tsx`
- Create: `web/tests/personal-opportunities.test.tsx`
- Create: `web/tests/personal-detail.test.tsx`
- Modify: `web/app/opportunities/[publicId]/fit-check/page.tsx`
- Modify: `web/app/opportunities/[publicId]/page.tsx`
- Modify: `web/components/site-header.tsx`
- Modify: `web/app/globals.css`
- Modify: `web/tests/fit-check-boundary.test.tsx`

**Interfaces:**
- Consumes: personal API DTOs and an HttpOnly `deepaha_phase6_session` cookie preloaded only by the
  disposable browser fixture; server-side calls translate it to backend bearer authorization.
- Produces: server-only `personalFetch<T>()`, server actions for profile/match/action writes and the
  four personal routes.

- [ ] **Step 1: Write failing UI/client tests**

```tsx
it("renders uncertainty and evidence without a matching percentage", async () => {
  render(await PersonalDetailPage(personalDetailProps));
  expect(screen.getByRole("heading", { name: "仍需确认" })).toBeVisible();
  expect(screen.getByText(/缺少：户籍地区/)).toBeVisible();
  expect(screen.getByRole("link", { name: "查看官方证据" })).toHaveAttribute("href", officialUrl);
  expect(document.body.textContent).not.toMatch(/匹配度|置信度|\d+%/);
});

it("profile form labels optional fields and supports skip", async () => {
  render(<ProfileForm initialState={null} action={vi.fn()} />);
  expect(screen.getByLabelText("专业（可跳过）")).toBeVisible();
  expect(screen.getByRole("checkbox", { name: "暂时跳过专业" })).toBeVisible();
  expect(screen.getByText(/只收集当前资格与行动所需信息/)).toBeVisible();
});
```

Add loading/empty/error tests, all four state labels, max-three cards, keyboard-native buttons/forms,
save/status/material states, official-link action, fixture/privacy notice and Phase 7/8 negative text.

- [ ] **Step 2: Run RED Web target**

Run: `cd web; corepack pnpm test -- personal-api-client profile personal-opportunities personal-detail fit-check-boundary`

Expected: fail because the personal modules/routes do not exist and the Phase 5 boundary is static.

- [ ] **Step 3: Implement server-only API client and actions**

```typescript
async function personalFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = (await cookies()).get("deepaha_phase6_session")?.value;
  if (!token) throw new PersonalApiError(401, "Personal session required");
  const response = await fetch(new URL(path, apiBaseUrl), {
    ...init,
    cache: "no-store",
    headers: { ...init.headers, Authorization: `Bearer ${token}`, Accept: "application/json" },
  });
  if (!response.ok) throw new PersonalApiError(response.status, "Personal request failed");
  return response.json() as Promise<T>;
}
```

Mark the module `server-only`. Server actions derive a fresh UUID idempotency key per submitted user
action and call `revalidatePath`; no token enters rendered props, URLs or client JavaScript.

- [ ] **Step 4: Implement progressive profile and personal routes**

Keep the Phase 5 color/typography tokens. Add only scoped classes for progressive form groups,
eligibility badges/explanation lists, priority cards and action panel. Use ordinary controls with
visible labels, 44px targets, focus rings, text plus color state, mobile single-column layout and
route-level loading/error recovery.

- [ ] **Step 5: Run Web tests and production build**

Run: `cd web; corepack pnpm lint; corepack pnpm typecheck; corepack pnpm test; corepack pnpm build`

Expected: all PASS; tests assert no token in rendered output and no percentage/feedback/reminder UI.

- [ ] **Step 6: Commit and push exact files**

```powershell
git add -- web/lib/personal-opportunities.ts web/app/personal-actions.ts web/components/profile-form.tsx web/components/eligibility-explanation.tsx web/components/personal-opportunity-card.tsx web/components/action-panel.tsx web/app/profile web/app/me web/app/opportunities/[publicId]/fit-check/page.tsx web/app/opportunities/[publicId]/page.tsx web/components/site-header.tsx web/app/globals.css web/tests/personal-api-client.test.ts web/tests/profile.test.tsx web/tests/personal-opportunities.test.tsx web/tests/personal-detail.test.tsx web/tests/fit-check-boundary.test.tsx
git commit -m "feat: add personal opportunity web flow"
git push
```

### Task 6: Governed synthetic fixtures and end-to-end integration

**Files:**
- Create: `backend/tests/fixtures/personal/phase6-users.json`
- Create: `backend/tests/fixtures/personal/phase6-users.manifest.json`
- Create: `backend/tests/personal/support.py`
- Create: `backend/tests/personal/seed_phase6_browser.py`
- Create: `backend/tests/integration/test_phase6_vertical_slice.py`
- Create: `backend/tests/integration/test_phase6_user_isolation.py`
- Modify: `backend/tests/public_catalog/support.py`

**Interfaces:**
- Consumes: Phase 5 three-item CC0 fixture and helper, Phase 4 RuleSet fixture patterns, personal
  models/services/API.
- Produces: `persist_phase6_fixture(session) -> Phase6FixtureIdentity` and browser seeder restricted
  to exact `127.0.0.1:55436/deepaha`.

- [ ] **Step 1: Write failing provenance and vertical-slice tests**

```python
def test_phase6_fixture_is_non_personal_synthetic_evidence() -> None:
    fixture = load_phase6_fixture()
    assert fixture.synthetic is True
    assert fixture.contains_personal_data is False
    assert fixture.business_truth is False
    assert fixture.release_qualification_eligible is False

@pytest.mark.integration
def test_official_to_action_vertical_slice(database) -> None:
    identity = persist_phase6_fixture(database)
    profile = save_minimum_profile(identity.user_a)
    priorities = run_matches(identity.user_a)
    detail = load_explanation(identity.user_a, priorities.items[0].public_id)
    action = save_and_prepare(identity.user_a, detail.public_id)
    assert profile.version == 1
    assert len(priorities.items) <= 3
    assert detail.official_url.host == "phase5-fixture.example.test"
    assert action.saved is True
```

- [ ] **Step 2: Run RED integration target in Phase 6 disposable services**

Run: `cd backend; uv run pytest -m integration tests/integration/test_phase6_vertical_slice.py tests/integration/test_phase6_user_isolation.py -q`

Expected: fail because fixture loader/seeder is absent.

- [ ] **Step 3: Implement deterministic fixture, manifest and seeder**

Use two fictional users, opaque disposable session tokens documented only in the fixture helper,
three current Phase 5 opportunities, approved deterministic RuleSets and profile variants covering
four states across targeted tests. Hash the JSON bytes in the manifest. Never use real names,
addresses, phone/email or upstream copyrighted content.

`seed_phase6_browser()` rejects any database URL not exactly host `127.0.0.1`, port `55436`, database
`deepaha`, and refuses a non-empty personal/public fixture database.

- [ ] **Step 4: Verify the complete personal integration set**

Run: `cd backend; uv run pytest -m integration tests/integration/test_phase6_profile_persistence.py tests/integration/test_phase6_match_replay.py tests/integration/test_phase6_personal_api.py tests/integration/test_phase6_vertical_slice.py tests/integration/test_phase6_user_isolation.py -q`

Expected: PASS with explicit fixture counts and zero cross-user disclosures.

- [ ] **Step 5: Commit and push exact files**

```powershell
git add -- backend/tests/fixtures/personal backend/tests/personal/support.py backend/tests/personal/seed_phase6_browser.py backend/tests/integration/test_phase6_vertical_slice.py backend/tests/integration/test_phase6_user_isolation.py backend/tests/public_catalog/support.py
git commit -m "test: cover phase 6 synthetic vertical slice"
git push
```

### Task 7: Isolated verifier, CI and real-browser evidence

**Files:**
- Create: `infra/compose.phase6.yaml`
- Create: `scripts/verify-phase6.ps1`
- Create: `backend/tests/test_phase6_verifier_scope.py`
- Create: `docs/gates/phase-6/browser-verification.md`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: all implementation/tests and browser seeder.
- Produces: exact-scope Phase 6 verification command, CI job `phase6-profile-action`, auditable
  non-sensitive browser observation record.

- [ ] **Step 1: Write failing verifier-scope tests**

```python
def test_phase6_verifier_uses_only_phase6_scope() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert "deepaha-phase6-" in script
    assert "55436" in script and "55004" in script
    for forbidden in ("55432", "55433", "55434", "55435", "55000", "55001", "55002", "55003"):
        assert forbidden not in script

def test_phase6_cleanup_is_exact_project_only() -> None:
    assert "--project-name $projectName" in script
    assert "docker system prune" not in script
```

- [ ] **Step 2: Run RED verifier target**

Run: `cd backend; uv run pytest tests/test_phase6_verifier_scope.py -q`

Expected: fail because Phase 6 compose/verifier files do not exist.

- [ ] **Step 3: Implement exact compose/verifier and CI job**

Copy the proven Phase 5 ownership-check structure, changing only project regex, ports, database
password and Phase 6 test targets. Before `up`, call `Assert-PortAvailableOrOwned 55436` and `55004`.
In `finally`, call only:

```powershell
docker compose --project-name $projectName --file $composeFile down --volumes --remove-orphans
```

CI `phase6-profile-action` starts PostgreSQL 18 and Moto on container-local ports, runs migration,
Phase 6 offline/integration/Web targets and the verifier-scope test. Keep all six inherited jobs.

- [ ] **Step 4: Run full isolated Phase 6 verifier**

Run: `powershell -ExecutionPolicy Bypass -File scripts/verify-phase6.ps1`

Expected: root regression, Phase 6 tests, migration cycle and Web build PASS; final output labels
fixture counts as synthetic, real users `0`, Release Qualification `NOT_STARTED`.

- [ ] **Step 5: Apply Playwright skill and perform real-browser checks**

Read `superpowers:verification-before-completion`, `playwright` and the UI skill
`references/pro-rules.md` before the browser run. Start only the exact Phase 6 compose project, seed
its disposable database, start backend and Web with fixture auth enabled, and use the bundled
Playwright wrapper.

Verify Chromium at 1440x900 and 375x812 plus keyboard-only navigation:

1. public detail -> fit check;
2. progressive profile with one skipped optional field;
3. generate 90-day results and observe at most three cards;
4. open an uncertain explanation and its official EvidenceRef;
5. save, update a material item and set `PREPARING`;
6. record official-link action and confirm fixture official destination;
7. invalidate the personal API once, observe error, restore it and retry;
8. verify no horizontal scroll, hidden focus, percentage, token or Phase 7/8 control.

Record viewport, commands, fixture IDs, expected/actual observations and cleanup in
`docs/gates/phase-6/browser-verification.md`. Do not commit screenshots, cookies, storage state,
tokens, browser profiles or build output.

- [ ] **Step 6: Commit and push exact verification files**

```powershell
git add -- infra/compose.phase6.yaml scripts/verify-phase6.ps1 backend/tests/test_phase6_verifier_scope.py .github/workflows/ci.yml docs/gates/phase-6/browser-verification.md
git commit -m "ci: verify phase 6 personal action slice"
git push
```

### Task 8: Gate evidence, reviews and final stacked draft delivery

**Files:**
- Create: `docs/gates/phase-6/README.md`
- Create: `docs/gates/phase-6/acceptance-results.md`
- Create: `docs/gates/phase-6/test-summary.md`
- Create: `docs/gates/phase-6/security-and-compliance.md`
- Create: `docs/gates/phase-6/operations.md`
- Create: `docs/gates/phase-6/deferred-decisions.md`
- Create: `docs/gates/phase-6/code-review.md`
- Modify: `docs/development/README.md`
- Modify: `docs/development/system-roadmap.md`
- Modify: `docs/development/architecture.md`
- Create: `docs/development/domain-contracts-v0.5.md`
- Modify: `docs/development/quality-and-release.md`
- Modify: Phase 6 design/plan only for exact closure evidence and checked task boxes.

**Interfaces:**
- Consumes: all local commands, browser observations, full diff, secret/artifact scans, draft PR and
  exact-SHA GitHub Actions evidence.
- Produces: truthful Phase 6 Gate package, final docs-only candidate commit, open/draft/unmerged
  stacked PR and exact-SHA CI record.

- [ ] **Step 1: Run verification-before-completion and full reviews**

Run the full Phase 6 verifier again and capture exact counts. Then run:

```powershell
git diff --check codex/phase-5-public-trust-layer...HEAD
git diff --name-status codex/phase-5-public-trust-layer...HEAD
git log --oneline --decorate codex/phase-5-public-trust-layer..HEAD
rg -n -i "(api[_-]?key|secret|token|password|cookie|session)\s*[:=]" --glob '!backend/uv.lock' --glob '!web/pnpm-lock.yaml'
rg -n "FeedbackEvent|Review Queue|Outbox|notification|reminder|匹配度|模型置信度|92%" backend/src web/app web/components contracts/schemas/v0.5.0
```

Inspect every hit in context. Record scope, authorization, privacy, secret, artifact, license,
migration, dependency, accessibility and full-diff conclusions. Any defect returns to RED and gets a
separate minimal fix commit.

- [ ] **Step 2: Write Gate evidence with truthful axes**

Until remote CI passes, record Implementation `IMPLEMENTED`, Engineering Gate `OPEN`, Release
Qualification `NOT_STARTED`, Contract Maturity `IMPLEMENTED`. State synthetic counts and real users
`0`; do not promote completion/action/coverage metrics.

- [ ] **Step 3: Commit and push Gate candidate docs**

```powershell
git add -- docs/gates/phase-6 docs/development/README.md docs/development/system-roadmap.md docs/development/architecture.md docs/development/domain-contracts-v0.5.md docs/development/quality-and-release.md docs/superpowers/specs/2026-08-22-phase-6-profile-match-personal-action-design.md docs/superpowers/plans/2026-08-22-phase-6-profile-match-personal-action.md
git commit -m "docs: record phase 6 engineering evidence"
git push
```

Stage only files that exist and changed; never replace the exact-path list with `git add .` or
`git add -A`.

- [ ] **Step 4: Create the stacked draft PR through the authenticated official GitHub API**

Create with title `Phase 6: profile, match and personal action`, head
`codex/phase-6-profile-match-personal-action`, base `codex/phase-5-public-trust-layer`,
`draft=true`. The body must list exact candidate SHA, local evidence, synthetic/real boundary,
four-axis state and explicit Phase 7/8 exclusions. Verify `open=true`, `draft=true`, `merged=false`
and exact base/head SHAs.

- [ ] **Step 5: Wait for every job on the final exact SHA**

Poll the official Actions run for exact `head_sha`, reporting only state changes. Required jobs are
the six inherited names plus `phase6-profile-action`. If a job fails, use
`superpowers:systematic-debugging`, reproduce locally, add a minimal fix commit, push, and restart
the exact-SHA evidence cycle.

- [ ] **Step 6: Close Engineering Gate only after exact-SHA success**

After the implementation candidate and its exact-SHA CI succeed, update Gate documents and design
closure evidence with that candidate SHA, run ID and every job conclusion. Set Engineering Gate
`CLOSED`; keep Release Qualification `NOT_STARTED` and Contract Maturity `IMPLEMENTED`, not
`STABLE`. Commit the docs-only closure, push, and wait again because the closure commit creates the
final handoff SHA. If that final run fails, the closure is not deliverable: use systematic debugging,
fix it, and repeat. After final success, update the PR body externally with the final handoff SHA/run;
do not create an infinite self-referential documentation-commit loop.

- [ ] **Step 7: Final repository/remote proof**

Run:

```powershell
git status --short --branch
git rev-parse HEAD
git rev-parse origin/codex/phase-6-profile-match-personal-action
git merge-base --is-ancestor 8d9b36c96174bffb303e7f981bd1775ebd8fa672 HEAD
git diff --check 8d9b36c96174bffb303e7f981bd1775ebd8fa672...HEAD
```

Expected: clean, local/remote exact SHA equal, ancestor command exits zero, diff check empty, stacked
draft PR open/draft/unmerged, and every job on the final exact SHA is `completed/success`.

## Execution selection

The user already selected continuous inline execution through the required skills. Continue in this
session with `superpowers:executing-plans`, preserving task order and task-level review checkpoints;
do not pause for the standard subagent/inline choice and do not dispatch subagents.
