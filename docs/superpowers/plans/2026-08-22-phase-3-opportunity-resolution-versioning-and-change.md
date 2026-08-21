# DeepAha Phase 3 Opportunity Resolution, Versioning and Change Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. The user explicitly forbids sub-agents. Use `superpowers:test-driven-development` for every behavior change, `superpowers:systematic-debugging` for failures, and `superpowers:verification-before-completion` before every commit or status claim.

**Goal:** Build a conservative, deterministic Phase 3 candidate that resolves evidenced Documents into stable Opportunities, appends replayable Versions/Events, and audits merge/split/reversal without crossing the still-open Phase 2 Gate.

**Architecture:** Add a compatible v0.3 contract and an Alembic expansion revision. Pure resolver/versioning/identity functions make deterministic decisions; a small SQLAlchemy application service persists immutable history and updates only the legacy Opportunity current projection in one transaction. Weak or conflicting matches become review candidates, never automatic hard merges.

**Tech Stack:** Python 3.14, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL 18.4, boto3/Moto 5.2.2, pytest, Ruff, mypy, PowerShell, Docker Compose, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-22-phase-3-opportunity-resolution-versioning-and-change-design.md`

## Global Constraints

- Work only in `C:\Users\LENOVO\.codex\worktrees\dbfb\DeepAha` on `codex/phase-3-opportunity-resolution`.
- Exact base is `64b09f508d9118a771195c4ab6449cc8487ab057`; design commit is `6b69183b922036e16ee5fb6ad5592af85e687bad`.
- Do not open, edit, switch, reset, stop, down, remove or otherwise access `D:\DeepAha\.worktrees\phase-2-source-ingestion`, branch `phase-2-source-ingestion`, or compose project `deepaha-phase2-live-gate`.
- Never use host ports `55432` or `55000`. Phase 3 PostgreSQL is `55433`; Phase 3 Moto is `55001`.
- Preserve `contracts/schemas/v0.1.0/` and `v0.2.0/` byte-for-byte and preserve v0.1/v0.2 import paths.
- v0.2 remains `PROPOSED`; v0.3 remains a candidate. The maximum final status is `IMPLEMENTED_PENDING_PHASE2_GATE`.
- Alembic is the only database schema creation path; PostgreSQL must be `18.x`.
- Default tests and CI must not access live sites, browsers or model APIs.
- Do not add LLM, Model Gateway, rules/eligibility, profiles, ranking, Redis/Valkey/Celery, pgvector, Playwright, Docling, OCR, API/UI, notifications, feedback, production cloud or Phase 2 collection changes.
- Fixtures are synthetic and contain no real business facts, user data, response bodies, credentials or unlicensed source originals.
- Every task follows RED -> minimal GREEN -> targeted verification -> risk-matched regression -> fresh verification -> commit -> push.
- Before each push, inspect actual commit and worktree status; never force-push.

---

### Task 1: Add compatible candidate v0.3 public contracts

**Files:**

- Create: `backend/src/deepaha/contracts/phase3.py`
- Modify: `backend/src/deepaha/contracts/export.py`
- Create: `backend/tests/contracts/test_phase3_contracts.py`
- Create: `contracts/examples/v0.3.0/phase-3-example.json`
- Create by exporter: `contracts/schemas/v0.3.0/*.schema.json`
- Create: `docs/development/domain-contracts-v0.3.md`

**Interfaces:**

- Consumes: `ContractModel`, `EntityId`, `Instant`, `Sha256`, `VersionNumber`, `OpportunityTypeV02`, `OpportunityStatus`, and all compatible v0.2 schemas.
- Produces: `OpportunityReviewStatus`, `OpportunityDocumentRole`, `OpportunityEventType`, `OpportunityAliasType`, `OpportunityIdentityActionType`, `OpportunityIdentityMemberRole`, `SnapshotField`, `ApplicationWindowSchema`, `OpportunitySnapshotSchema`, `OpportunityFieldEvidenceSchema`, `OpportunityFieldChangeSchema`, `OpportunityVersionSchemaV03`, `OpportunityEventSchemaV03`, `DocumentOpportunityLinkSchema`, `OpportunityResolutionCandidateSchema`, `OpportunityAliasSchemaV03`, `OpportunityIdentityMemberSchema`, `OpportunityIdentityActionSchema`, `PHASE3_SCHEMAS`, `render_phase3_schemas()`, `write_phase3_schemas()`.

- [ ] **Step 1: Write the failing contract tests**

Before the test body, record the bugs these tests catch: old schema mutation, missing event-chain validation, identity-action shape drift, EvidenceRef-free high-impact records, and non-deterministic exporter output.

```python
def test_v03_event_requires_a_continuous_version_transition() -> None:
    with pytest.raises(ValidationError, match="CREATED"):
        OpportunityEventSchemaV03.model_validate(
            event_values(event_type="CREATED", from_version=1, to_version=2)
        )


def test_identity_merge_requires_one_target_and_at_least_one_source() -> None:
    with pytest.raises(ValidationError, match="TARGET"):
        OpportunityIdentityActionSchema.model_validate(
            identity_action_values(members=[member_values(role="SOURCE")])
        )


def test_old_schema_bytes_remain_unchanged() -> None:
    for directory, rendered in (
        (V01_SCHEMA_DIRECTORY, render_phase1_schemas()),
        (V02_SCHEMA_DIRECTORY, render_phase2_schemas()),
    ):
        assert {path.name: path.read_bytes() for path in directory.glob("*.json")} == rendered
```

The same file contains literal tests named:

```text
test_snapshot_rejects_duplicate_urls_and_locations
test_field_change_rejects_equal_before_and_after
test_version_requires_nonempty_changes_and_matching_evidence
test_created_event_requires_null_from_version_and_to_version_one
test_noncreated_event_requires_next_version
test_link_end_fields_are_both_present_or_both_absent
test_candidate_starts_pending_and_rejects_extra_fields
test_alias_requires_source_for_external_id
test_reversal_requires_reversal_of_and_copied_members
test_nonreversal_forbids_reversal_of
test_v03_example_validates_with_pydantic_and_json_schema
test_v03_renderer_matches_checked_in_schema_bytes
test_v03_export_writes_only_to_v03_directory
```

- [ ] **Step 2: Run the contract test and verify RED**

Run:

```powershell
Set-Location backend
uv run pytest tests/contracts/test_phase3_contracts.py -v
```

Expected: collection fails because `deepaha.contracts.phase3` does not exist. If it fails for a typo or fixture syntax error, fix the test until the missing production module is the reason.

- [ ] **Step 3: Implement exact v0.3 contract models**

Use `StrEnum`, `extra="forbid"`, `JsonValue`, tuple fields, field validators and model validators. The core event validator is:

```python
class OpportunityEventSchemaV03(ContractModel):
    event_id: EntityId
    opportunity_id: EntityId
    from_version: VersionNumber | None
    to_version: VersionNumber
    event_type: OpportunityEventType
    changed_fields: tuple[SnapshotField, ...] = Field(min_length=1)
    changes: tuple[OpportunityFieldChangeSchema, ...] = Field(min_length=1)
    source_document_id: EntityId
    source_evidence_ref_id: EntityId
    detected_at: Instant

    @model_validator(mode="after")
    def require_version_transition(self) -> Self:
        if self.event_type is OpportunityEventType.CREATED:
            if self.from_version is not None or self.to_version != 1:
                raise ValueError("CREATED requires from_version=null and to_version=1")
        elif self.from_version is None or self.to_version != self.from_version + 1:
            raise ValueError("non-CREATED event requires a continuous version transition")
        if tuple(dict.fromkeys(self.changed_fields)) != self.changed_fields:
            raise ValueError("changed_fields must be unique and ordered")
        if tuple(change.field_path for change in self.changes) != self.changed_fields:
            raise ValueError("changed_fields must match changes order")
        return self
```

The identity validator implements the exact member cardinalities from the spec. Reversal members are required and validated structurally; matching them to the referenced database action is a Task 6 service check.

- [ ] **Step 4: Extend deterministic export without changing old behavior**

Add `PHASE3_SCHEMAS` with all v0.2-compatible objects plus:

```python
PHASE3_SCHEMAS: dict[str, type[BaseModel]] = dict(PHASE2_SCHEMAS)
PHASE3_SCHEMAS.update({
    "opportunity-version.schema.json": OpportunityVersionSchemaV03,
    "opportunity-event.schema.json": OpportunityEventSchemaV03,
    "document-opportunity-link.schema.json": DocumentOpportunityLinkSchema,
    "opportunity-resolution-candidate.schema.json": OpportunityResolutionCandidateSchema,
    "opportunity-alias.schema.json": OpportunityAliasSchemaV03,
    "opportunity-identity-action.schema.json": OpportunityIdentityActionSchema,
})
```

`--version` choices become `0.1.0|0.2.0|0.3.0`; omitted still exports v0.1. Write the example with one value for every `PHASE3_SCHEMAS` key, fixed UUIDv7 values, `https://example.gov/` URLs and synthetic wording that asserts no real business fact. Keep fixture provenance metadata in the resolver fixture rather than adding non-schema keys to this contract example.

Run:

```powershell
$previousPhase3PythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = "src"
    uv run python -m deepaha.contracts.export .. --version 0.3.0
} finally {
    $env:PYTHONPATH = $previousPhase3PythonPath
}
uv run pytest tests/contracts/test_phase1_contracts.py tests/contracts/test_phase2_contracts.py tests/contracts/test_phase3_contracts.py -v
```

- [ ] **Step 5: Write the candidate contract document**

`domain-contracts-v0.3.md` records status `PROPOSED_IMPLEMENTATION_BLOCKED_BY_PHASE2_GATE`, exact fields, compatibility rules, precedence table, no-LLM boundary, transition invariants, and the rule that no implementation evidence can mark it STABLE while Phase 2 remains open.

- [ ] **Step 6: Verify GREEN and compatibility**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest tests/contracts -v
Set-Location ..
git diff --check
git status --short
```

Expected: all contract tests pass; only Task 1 files are modified; old schema directories have zero diff.

- [ ] **Step 7: Commit and push Task 1**

```powershell
git add backend/src/deepaha/contracts/phase3.py backend/src/deepaha/contracts/export.py backend/tests/contracts/test_phase3_contracts.py contracts/examples/v0.3.0 contracts/schemas/v0.3.0 docs/development/domain-contracts-v0.3.md
git diff --cached --check
git commit -m "feat(contracts): define phase 3 opportunity history"
git push
```

---

### Task 2: Add the Phase 3 expansion migration, ORM and isolated services

**Files:**

- Create: `infra/compose.phase3.yaml`
- Create: `backend/migrations/versions/20260822_0003_phase3_opportunity_history.py`
- Modify: `backend/src/deepaha/opportunities/models.py`
- Modify: `backend/src/deepaha/documents/models.py`
- Modify: `backend/src/deepaha/db/models.py`
- Modify: `backend/tests/integration/test_migrations.py`
- Create: `backend/tests/integration/test_phase3_persistence_contract.py`

**Interfaces:**

- Consumes: Phase 1/2 tables and `Base.metadata`.
- Produces ORM `OpportunityVersion`, `OpportunityEvent`, `DocumentOpportunityLink`, `OpportunityResolutionCandidate`, `OpportunityAlias`, `OpportunityIdentityAction`, `OpportunityIdentityActionMember`, revision `20260822_0003`, and a Phase 3-only PostgreSQL/Moto runtime.

- [ ] **Step 1: Create and validate the isolated Compose configuration**

This configuration is explicitly required by the user and is test infrastructure, not application behavior. Its exact contents are:

```yaml
services:
  postgres:
    image: postgres:18.4-alpine3.23
    environment:
      POSTGRES_DB: deepaha
      POSTGRES_USER: deepaha
      POSTGRES_PASSWORD: deepaha_phase3_local_only
    ports:
      - "127.0.0.1:55433:5432"
    tmpfs:
      - /var/lib/postgresql:rw,noexec,nosuid,size=512m,mode=1777
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U deepaha -d deepaha"]
      interval: 2s
      timeout: 2s
      retries: 30
  s3:
    image: motoserver/moto:5.2.2
    ports:
      - "127.0.0.1:55001:5000"
```

Validate effective config without starting services:

```powershell
docker compose -f infra/compose.phase3.yaml -p deepaha-phase3-config config
```

Read the output and confirm it contains only published ports 55433/55001.

- [ ] **Step 2: Write RED persistence and migration tests**

```python
def test_current_version_must_reference_the_same_opportunity_version(session: Session) -> None:
    opportunity = make_opportunity(current_version=1)
    session.add(opportunity)
    with pytest.raises(IntegrityError):
        session.flush()


def test_event_rejects_evidence_from_another_document(session: Session) -> None:
    graph = persist_two_document_graph(session)
    session.add(make_event(graph, source_evidence_ref_id=graph.other_evidence.evidence_ref_id))
    with pytest.raises(IntegrityError):
        session.flush()


def test_one_document_cannot_have_two_active_opportunity_links(session: Session) -> None:
    graph = persist_two_opportunities_for_one_document(session)
    session.add_all([make_link(graph.first), make_link(graph.second)])
    with pytest.raises(IntegrityError):
        session.flush()
```

The same file has literal tests for UUIDv7, controlled enum values, nonempty JSON arrays, SHA format, duplicate version hash, one event per to_version, candidate arrays, alias scopes, reversal null shape, and member roles.

Extend migration tests with:

```python
PHASE3_TABLES = {
    "opportunity_versions", "opportunity_events", "document_opportunity_links",
    "opportunity_resolution_candidates", "opportunity_aliases",
    "opportunity_identity_actions", "opportunity_identity_action_members",
}
```

The isolated round trip is exactly `0001 -> 0002 -> 0003 -> 0002 -> 0003`. A second test inserts one v0.3 version and proves downgrade raises `cannot downgrade Phase 3` while the row remains.

- [ ] **Step 3: Start only Phase 3 services and verify RED**

```powershell
$phase3Task2Project = "deepaha-phase3-task2-$PID"
docker compose -f infra/compose.phase3.yaml -p $phase3Task2Project up -d --wait postgres s3
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_phase3_local_only@127.0.0.1:55433/deepaha"
$env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55001"
Set-Location backend
uv run pytest tests/integration/test_migrations.py tests/integration/test_phase3_persistence_contract.py -m integration -v
```

Expected: import/collection failure because Phase 3 ORM classes/revision are absent. Verify `docker compose -p $phase3Task2Project ps` names only the Phase 3 project.

- [ ] **Step 4: Implement ORM tables and the migration**

Use typed mappings and existing naming conventions. Add this deferred FK to `Opportunity.__table_args__`:

```python
ForeignKeyConstraint(
    ["opportunity_id", "current_version"],
    ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
    name="fk_opportunities_current_version_opportunity_versions",
    ondelete="RESTRICT",
    deferrable=True,
    initially="DEFERRED",
)
```

Use JSONB only for snapshot/field evidence/changes/candidate arrays. Add database checks for JSON kind and nonempty arrays. Add a partial unique index:

```python
Index(
    "uq_document_opportunity_links_active_document",
    "document_id",
    unique=True,
    postgresql_where=text("ended_at is null"),
)
```

Migration downgrade checks each Phase 3 table with `select exists(...)` and raises before any DDL when data exists. Do not query or alter Phase 2 live services.

- [ ] **Step 5: Verify migration round trip and metadata**

```powershell
uv run alembic upgrade head
uv run pytest tests/integration/test_migrations.py tests/integration/test_phase2_persistence_contract.py tests/integration/test_phase3_persistence_contract.py -m integration -v
uv run alembic check
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
```

- [ ] **Step 6: Stop only Task 2 services, verify scope, commit and push**

```powershell
Set-Location ..
docker compose -f infra/compose.phase3.yaml -p $phase3Task2Project down --remove-orphans
git diff --check
git status --short
git add infra/compose.phase3.yaml backend/migrations/versions/20260822_0003_phase3_opportunity_history.py backend/src/deepaha/opportunities/models.py backend/src/deepaha/db/models.py backend/tests/integration/test_migrations.py backend/tests/integration/test_phase3_persistence_contract.py
git diff --cached --check
git commit -m "feat(db): persist phase 3 opportunity history"
git push
```

---

### Task 3: Implement stable identity keys and the conservative pure Resolver

**Files:**

- Create: `backend/src/deepaha/opportunities/types.py`
- Create: `backend/src/deepaha/opportunities/identity.py`
- Create: `backend/src/deepaha/opportunities/resolver.py`
- Modify: `backend/src/deepaha/opportunities/__init__.py`
- Create: `backend/tests/opportunities/__init__.py`
- Create: `backend/tests/opportunities/test_resolver.py`
- Create: `backend/tests/fixtures/opportunities/phase3-resolution-cases.json`

**Interfaces:**

- Produces `UNSET`, `OpportunityPatch`, `ResolutionDocument`, `ResolutionIndex`, `ResolutionDecision`, `normalize_identity_text()`, `normalize_official_url()`, `stable_public_id_for_key()`, `weak_fingerprint()`, and `resolve_document()`.
- No SQLAlchemy, network, object store, LLM or clock reads are allowed in the pure Resolver.

- [ ] **Step 1: Add the fixed synthetic fixture and RED tests**

Fixture metadata and cases are literal:

```json
{
  "schema_version": "0.3.0",
  "synthetic": true,
  "contains_business_facts": false,
  "license": "CC0-1.0 synthetic fixture",
  "cases": [
    {"case_id": "primary", "expected": "CREATED"},
    {"case_id": "duplicate", "expected": "LINKED"},
    {"case_id": "attachment", "expected": "LINKED"},
    {"case_id": "position_table", "expected": "LINKED"},
    {"case_id": "correction", "expected": "LINKED"},
    {"case_id": "deadline_extension", "expected": "LINKED"},
    {"case_id": "cancellation", "expected": "LINKED"},
    {"case_id": "lower_priority_conflict", "expected": "NEEDS_REVIEW"},
    {"case_id": "possible_false_merge", "expected": "NEEDS_REVIEW"}
  ]
}
```

Every case object contains fixed UUIDv7s, timestamps, source tier, document role, `external_id`, relation references and a typed field patch. The primary case uses source ID `019b0000-0000-7000-8000-000000000001` and normalized external ID `deepaha-2026-001`, so its primary identity key is `external:019b0000-0000-7000-8000-000000000001:deepaha-2026-001`. Its expected stable public ID is the literal SHA-256 prefix below and is not computed with the production helper in the assertion.

```python
def test_primary_official_document_creates_literal_stable_public_id() -> None:
    decision = resolve_document(primary_document(), ResolutionIndex.empty())
    assert decision.disposition == ResolutionDisposition.CREATED
    assert decision.public_id == "opp_63be197cc6ef3632650c5f69b5938f0b"


def test_same_title_without_shared_strong_key_never_hard_merges() -> None:
    decision = resolve_document(false_merge_document(), index_with_weak_candidate())
    assert decision.disposition == ResolutionDisposition.NEEDS_REVIEW
    assert decision.reason_codes == ("POSSIBLE_DUPLICATE",)


def test_conflicting_strong_keys_never_choose_by_input_order() -> None:
    first = resolve_document(conflicting_document(), conflicting_index())
    second = resolve_document(reverse_references(conflicting_document()), conflicting_index())
    assert first == second
    assert first.reason_codes == ("STRONG_KEY_CONFLICT",)
```

Additional literal tests cover missing stable key, non-primary create attempt, missing attachment relation, community/secondary sources, URL query preservation, external ID source scoping, duplicate input replay and deterministic candidate sorting.

- [ ] **Step 2: Verify RED**

```powershell
Set-Location backend
uv run pytest tests/opportunities/test_resolver.py -v
```

Expected: missing `deepaha.opportunities.types`/`resolver` import.

- [ ] **Step 3: Implement frozen input/output types**

```python
class _Unset:
    __slots__ = ()


UNSET = _Unset()


@dataclass(frozen=True, slots=True)
class OpportunityPatch:
    canonical_title: str | _Unset = UNSET
    type: OpportunityTypeV02 | _Unset = UNSET
    issuer_name: str | _Unset = UNSET
    jurisdiction: str | None | _Unset = UNSET
    status: OpportunityStatus | _Unset = UNSET
    published_at: datetime | None | _Unset = UNSET
    application_window: ApplicationWindowSchema | _Unset = UNSET
    application_url: str | None | _Unset = UNSET
    attachment_urls: tuple[str, ...] | _Unset = UNSET
    locations: tuple[str, ...] | _Unset = UNSET
```

`ResolutionIndex` stores immutable maps for reference Document, external key and URL key plus weak candidates. Its constructor sorts all tuple values.

- [ ] **Step 4: Implement normalization, stable public ID and Resolver**

`stable_public_id_for_key()` is exactly:

```python
def stable_public_id_for_key(identity_key: str) -> str:
    digest = sha256(f"deepaha:opportunity:v0.3:{identity_key}".encode()).hexdigest()
    return f"opp_{digest[:32]}"
```

The Resolver follows the spec order: validate evidence-bearing input, resolve reference/external/URL strong keys, candidateize conflicts, candidateize weak duplicates, allow official-primary main create, and require strong relation for non-primary roles. It returns values only and performs no write.

- [ ] **Step 5: Verify GREEN and mutation behavior**

```powershell
uv run pytest tests/opportunities/test_resolver.py -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
```

Mutation check: temporarily allow a unique weak candidate to return LINKED; run
`test_same_title_without_shared_strong_key_never_hard_merges` and observe failure; restore conservative behavior and rerun green.

- [ ] **Step 6: Commit and push Task 3**

```powershell
Set-Location ..
git diff --check
git add backend/src/deepaha/opportunities backend/tests/opportunities backend/tests/fixtures/opportunities/phase3-resolution-cases.json
git diff --cached --check
git commit -m "feat(opportunities): resolve evidenced documents conservatively"
git push
```

---

### Task 4: Implement pure version planning, field diffs and replay

**Files:**

- Create: `backend/src/deepaha/opportunities/versioning.py`
- Modify: `backend/src/deepaha/opportunities/types.py`
- Create: `backend/tests/opportunities/test_versioning.py`
- Create: `backend/tests/opportunities/test_replay.py`

**Interfaces:**

- Produces `VersionState`, `VersionPlan`, `VersionConflict`, `derive_precedence()`, `canonical_content_sha256()`, `plan_version()`, `classify_event_type()`, and `replay_opportunity_state()`.

- [ ] **Step 1: Write RED precedence, diff, event and replay tests**

```python
def test_latest_official_deadline_extension_wins_and_emits_deadline_event() -> None:
    plan = plan_version(current_state(), official_deadline_extension())
    assert isinstance(plan, VersionPlan)
    assert plan.version == 2
    assert plan.event_type is OpportunityEventType.DEADLINE_CHANGED
    assert [(change.field_path.value, change.before, change.after) for change in plan.changes] == [
        ("application_window.closes_on", "2026-09-10", "2026-09-20")
    ]


def test_lower_priority_conflict_never_partially_applies_patch() -> None:
    conflict = plan_version(current_state(), lower_priority_conflicting_patch())
    assert conflict == VersionConflict(reason_codes=("LOWER_PRIORITY_CONFLICT",))


def test_replay_rejects_a_changed_before_value() -> None:
    versions, events = valid_history()
    events[1] = replace(events[1], changes=(wrong_before_change(),))
    with pytest.raises(ReplayError, match="before"):
        replay_opportunity_state(versions, events)
```

Literal test names also cover precedence values 600/500/400/300/250, same value no-op, same precedence newer time, same-time conflict, cancellation, reopening, attachment replacement, correction, sorted canonical JSON, content hash literal, missing version, duplicate event, hash drift and deterministic replay.

- [ ] **Step 2: Verify RED**

```powershell
Set-Location backend
uv run pytest tests/opportunities/test_versioning.py tests/opportunities/test_replay.py -v
```

Expected: missing `deepaha.opportunities.versioning`.

- [ ] **Step 3: Implement canonicalization and precedence**

Use a recursive conversion that accepts only JSON values, UUID, date, aware datetime and StrEnum. Normalize datetime to UTC `Z`, sort dict keys, and serialize with:

```python
json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
```

Reject naive time and unsupported objects. `derive_precedence()` maps the exact table in the spec; Phase 3 never accepts a caller-provided rank.

- [ ] **Step 4: Implement all-or-nothing version planning**

Build changes in `SnapshotField` enum order. If any differing field loses precedence or conflicts at equal time, return `VersionConflict` and discard the complete tentative patch. Version 1 includes only non-null/explicitly set fields as `before=None` changes. A semantic no-op returns `None`.

Event classification uses the exact priority from the spec. `content_sha256` covers snapshot and sorted field evidence only.

- [ ] **Step 5: Implement strict replay**

Replay applies event changes to an initially empty mapping, checks literal `before`, validates version/event continuity, reconstructs snapshot and field evidence, recalculates every hash, and returns the latest `VersionState`. It never repairs or skips malformed history.

- [ ] **Step 6: Verify GREEN and regression**

```powershell
uv run pytest tests/opportunities/test_versioning.py tests/opportunities/test_replay.py -v
uv run pytest tests/opportunities/test_resolver.py tests/contracts/test_phase3_contracts.py -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
```

- [ ] **Step 7: Commit and push Task 4**

```powershell
Set-Location ..
git diff --check
git add backend/src/deepaha/opportunities/versioning.py backend/src/deepaha/opportunities/types.py backend/tests/opportunities/test_versioning.py backend/tests/opportunities/test_replay.py
git diff --cached --check
git commit -m "feat(opportunities): version and replay field changes"
git push
```

---

### Task 5: Persist the deterministic resolution/version vertical slice

**Files:**

- Create: `backend/src/deepaha/opportunities/service.py`
- Modify: `backend/src/deepaha/opportunities/__init__.py`
- Modify: `backend/src/deepaha/opportunities/models.py`
- Create: `backend/tests/integration/__init__.py`
- Create: `backend/tests/integration/test_opportunity_resolution_service.py`
- Create: `backend/tests/integration/test_phase3_resolution_replay.py`

**Interfaces:**

- Produces `OpportunityResolutionService`, `ResolutionResult`, `resolve()`, and `load_resolution_index()`.
- Consumes the fixed synthetic fixture, pure Resolver and pure Version planner.

- [ ] **Step 1: Write RED vertical integration tests**

```python
def test_notice_attachment_table_correction_extension_and_cancel_share_one_public_id(
    service: OpportunityResolutionService,
) -> None:
    results = [service.resolve(command) for command in phase3_happy_path_commands()]
    assert {result.public_id for result in results} == {
        "opp_63be197cc6ef3632650c5f69b5938f0b"
    }
    assert [result.event_type for result in results if result.event_type] == [
        "CREATED", "ATTACHMENT_REPLACED", "ATTACHMENT_REPLACED", "CORRECTED",
        "DEADLINE_CHANGED", "CANCELLED",
    ]


def test_conflict_and_false_merge_candidates_do_not_change_projection(
    service: OpportunityResolutionService,
    session_factory: sessionmaker[Session],
) -> None:
    before = current_projection(session_factory)
    conflict = service.resolve(lower_priority_conflict_command())
    false_merge = service.resolve(false_merge_command())
    assert conflict.disposition == false_merge.disposition == "NEEDS_REVIEW"
    assert current_projection(session_factory) == before
```

Additional tests prove Document/EvidenceRef mismatch rolls back, same Document replay is idempotent, duplicate announcement links without a version, no-op patch creates no event, public ID collision candidateizes, and a transaction failure leaves all old versions/events intact.

- [ ] **Step 2: Start only Phase 3 services and verify RED**

```powershell
$phase3Task5Project = "deepaha-phase3-task5-$PID"
docker compose -f infra/compose.phase3.yaml -p $phase3Task5Project up -d --wait postgres s3
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_phase3_local_only@127.0.0.1:55433/deepaha"
$env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55001"
Set-Location backend
uv run pytest tests/integration/test_opportunity_resolution_service.py tests/integration/test_phase3_resolution_replay.py -m integration -v
```

Expected: missing `OpportunityResolutionService`.

- [ ] **Step 3: Implement the transaction service**

The constructor has exact keyword-only parameters `session_factory: sessionmaker[Session]`, `clock: Callable[[], datetime]`, `id_factory: Callable[[], UUID] = uuid7`, and `resolver_version: str = "0.3.0"`. Its public method is `resolve(command: ResolutionDocument) -> ResolutionResult`.

Implementation order exactly follows spec section 11.2. Validate `(evidence_ref_id, document_id)` before calling Resolver. Candidate commits without formal version. CREATED inserts Opportunity with null current version, link/aliases, Version 1/Event CREATED, then updates current projection. LINKED inserts link before version planning. Conflict saves candidate and does not update projection. The service owns commit/rollback and returns detached value objects only.

- [ ] **Step 4: Verify full synthetic replay**

Run the fixture twice in two freshly created temporary databases. Compare these literal outputs, excluding internal random UUIDv7 IDs:

```text
public_id
ordered version numbers
ordered content_sha256 values
ordered event types
ordered changed field paths
candidate reason codes
final legacy projection
```

```powershell
uv run pytest tests/integration/test_opportunity_resolution_service.py tests/integration/test_phase3_resolution_replay.py -m integration -v
uv run alembic check
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
```

- [ ] **Step 5: Stop only Task 5 services, commit and push**

```powershell
Set-Location ..
docker compose -f infra/compose.phase3.yaml -p $phase3Task5Project down --remove-orphans
git diff --check
git add backend/src/deepaha/opportunities/service.py backend/src/deepaha/opportunities/__init__.py backend/src/deepaha/opportunities/models.py backend/tests/integration/__init__.py backend/tests/integration/test_opportunity_resolution_service.py backend/tests/integration/test_phase3_resolution_replay.py docs/superpowers/plans/2026-08-22-phase-3-opportunity-resolution-versioning-and-change.md
git diff --cached --check
git commit -m "feat(opportunities): persist deterministic resolution history"
git push
```

---

### Task 6: Implement merge, split and reversal audit/replay

**Files:**

- Modify: `backend/src/deepaha/opportunities/identity.py`
- Modify: `backend/src/deepaha/opportunities/service.py`
- Create: `backend/tests/opportunities/test_identity_replay.py`
- Create: `backend/tests/integration/test_opportunity_identity_service.py`

**Interfaces:**

- Produces `IdentityActionRecord`, `IdentityState`, `IdentityReplayError`, `replay_identity_state()`, `resolve_canonical_opportunity_id()`, `merge()`, `split()`, and `reverse_identity_action()`.

- [ ] **Step 1: Write RED pure identity tests**

```python
def test_merge_reversal_restores_source_public_identity_without_deleting_history() -> None:
    merged = replay_identity_state((merge_action(),))
    reversed_state = replay_identity_state((merge_action(), merge_reversal()))
    assert merged.canonical_by_opportunity[SOURCE_ID] == TARGET_ID
    assert reversed_state.canonical_by_opportunity[SOURCE_ID] == SOURCE_ID
    assert reversed_state.active_action_ids == frozenset()


def test_split_reversal_removes_active_children_but_preserves_child_identities() -> None:
    state = replay_identity_state((split_action(), split_reversal()))
    assert PARENT_ID not in state.split_children_by_parent
    assert state.canonical_by_opportunity[CHILD_ONE_ID] == CHILD_ONE_ID
    assert state.canonical_by_opportunity[CHILD_TWO_ID] == CHILD_TWO_ID
```

Literal tests also reject merge cycles, multiple active targets, duplicate reversal, reversal of reversal, wrong reversal type, member mismatch and nondeterministic action ordering.

- [ ] **Step 2: Write RED database service tests**

```python
def test_merge_split_reversal_never_delete_public_ids_or_history(identity_service) -> None:
    baseline = persisted_identity_counts()
    merge_id = identity_service.merge(
        target_id=MERGE_TARGET_ID,
        source_ids=(MERGE_SOURCE_ID,),
        document_id=DOCUMENT_ID,
        evidence_ref_id=EVIDENCE_REF_ID,
        actor="phase3-synthetic-test",
        reason="synthetic duplicate correction",
    )
    identity_service.reverse_identity_action(
        action_id=merge_id,
        document_id=DOCUMENT_ID,
        evidence_ref_id=EVIDENCE_REF_ID,
        actor="phase3-synthetic-test",
        reason="synthetic merge reversal",
    )
    split_id = identity_service.split(
        parent_id=SPLIT_PARENT_ID,
        child_ids=(CHILD_ONE_ID, CHILD_TWO_ID),
        document_id=DOCUMENT_ID,
        evidence_ref_id=EVIDENCE_REF_ID,
        actor="phase3-synthetic-test",
        reason="synthetic composite opportunity correction",
    )
    identity_service.reverse_identity_action(
        action_id=split_id,
        document_id=DOCUMENT_ID,
        evidence_ref_id=EVIDENCE_REF_ID,
        actor="phase3-synthetic-test",
        reason="synthetic split reversal",
    )
    after = persisted_identity_counts()
    assert after.opportunities == baseline.opportunities
    assert after.versions == baseline.versions
    assert after.events == baseline.events
    assert after.public_ids == baseline.public_ids
    assert after.identity_actions == 4
```

Other integration tests prove actor/reason required, evidence/document pairing, source/target existence, no action on failed cycle, copied reversal members, alias canonical resolution after merge/reversal, and deterministic database reload/replay.

- [ ] **Step 3: Verify RED**

```powershell
Set-Location backend
uv run pytest tests/opportunities/test_identity_replay.py -v
```

Then with Phase 3 scoped services:

```powershell
$phase3Task6Project = "deepaha-phase3-task6-$PID"
docker compose -f ../infra/compose.phase3.yaml -p $phase3Task6Project up -d --wait postgres s3
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_phase3_local_only@127.0.0.1:55433/deepaha"
uv run pytest tests/integration/test_opportunity_identity_service.py -m integration -v
```

Expected: pure and service functions are absent.

- [ ] **Step 4: Implement append-only identity replay and service operations**

Sort by `(occurred_at, action_id.hex)`. First build reversal map and validate it, then apply active MERGE/SPLIT actions. Detect cycles by following canonical targets before accepting a merge. `resolve_canonical_opportunity_id()` path-compresses only in an in-memory dict; it never writes or changes action rows.

Service methods insert action and member rows in one transaction. A reversal reloads original members, compares the requested action type, copies the exact members, and inserts a new action referencing the original. It never deletes or updates the original action.

- [ ] **Step 5: Verify GREEN, mutation and regressions**

```powershell
uv run pytest tests/opportunities/test_identity_replay.py -v
uv run pytest tests/integration/test_opportunity_identity_service.py -m integration -v
uv run pytest tests/opportunities tests/integration/test_opportunity_resolution_service.py tests/integration/test_phase3_resolution_replay.py -v
uv run alembic check
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
```

Mutation check: temporarily allow a second reversal of the same action; observe the duplicate-reversal test fail; restore and rerun green.

- [ ] **Step 6: Stop only Task 6 services, commit and push**

```powershell
Set-Location ..
docker compose -f infra/compose.phase3.yaml -p $phase3Task6Project down --remove-orphans
git diff --check
git add backend/src/deepaha/opportunities/identity.py backend/src/deepaha/opportunities/service.py backend/tests/opportunities/test_identity_replay.py backend/tests/integration/test_opportunity_identity_service.py
git diff --cached --check
git commit -m "feat(opportunities): audit identity merge and split actions"
git push
```

---

### Task 7: Add the Phase 3 verifier, CI and truthful blocked Gate evidence

**Files:**

- Create: `scripts/verify-phase3.ps1`
- Modify: `.github/workflows/ci.yml`
- Create: `docs/gates/phase-3/README.md`
- Create: `docs/gates/phase-3/acceptance-results.md`
- Create: `docs/gates/phase-3/test-summary.md`
- Create: `docs/gates/phase-3/resolver-evaluation-summary.md`
- Create: `docs/gates/phase-3/security-and-compliance.md`
- Create: `docs/gates/phase-3/operations.md`
- Create: `docs/gates/phase-3/deferred-decisions.md`
- Modify: `docs/development/README.md`
- Modify: `docs/development/system-roadmap.md`
- Modify: `README.md`

**Interfaces:**

- Produces a Phase 3-only local verification entry point and matching `phase3-resolution` GitHub Actions job.
- Gate evidence distinguishes `IMPLEMENTED`, `LOCALLY_VERIFIED`, `REMOTE_CI`, and `BLOCKED_BY_PHASE2` without closing any Gate.

- [ ] **Step 1: Write the scoped verifier**

The script defines:

```powershell
$phase3ComposeFile = Join-Path $projectRoot "infra/compose.phase3.yaml"
$phase3ComposeProject = "deepaha-phase3-$PID"
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_phase3_local_only@127.0.0.1:55433/deepaha"
$env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55001"
```

It runs `scripts/verify.ps1`, starts only this project, performs locked sync, Alembic upgrade, all integration tests, Phase 1/2/3 contract tests, opportunities tests and `alembic check`. In `finally`, it executes only:

```powershell
docker compose -f $phase3ComposeFile -p $phase3ComposeProject down --remove-orphans
```

It must not call `verify-phase1.ps1`, `verify-phase2.ps1`, use `-v`, enumerate projects, or reference 55432/55000.

- [ ] **Step 2: Verify the verifier RED-GREEN**

First run with one expected fixture `content_sha256` intentionally changed in the test fixture expectation, not in production history. Confirm nonzero and inspect that only `deepaha-phase3-$PID` is cleaned. Restore the expected hash and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-phase3.ps1
```

Record actual exit code, test counts, migration head, PostgreSQL version, Moto version and Alembic check output. Never record a planned count.

- [ ] **Step 3: Add matching CI**

Add `phase3-resolution` with PostgreSQL 18.4 and Moto 5.2.2 services, Python 3.14, locked sync, Alembic upgrade, Phase 3 unit/contract/integration tests and `alembic check`. Test-only environment constants use CI ports 5432/5000 and are explicitly labelled disposable. Do not set live permission.

- [ ] **Step 4: Create truthful candidate Gate evidence**

`docs/gates/phase-3/README.md` begins:

```text
Gate status: BLOCKED_BY_PHASE2
Implementation status: IMPLEMENTED_PENDING_PHASE2_GATE
v0.3 contract status: PROPOSED
Phase 2 prerequisite: OPEN
```

Populate local evidence only from Step 2 output. Before remote CI, record it as PENDING. `acceptance-results.md` maps every Phase 3 exit to a test/command and explicitly states which evidence is synthetic. `resolver-evaluation-summary.md` reports fixture counts, not `>=98%` real-world precision. `deferred-decisions.md` copies every excluded capability and the post-Phase2 rebase/reverify sequence.

- [ ] **Step 5: Run fresh full local verification and scope/security/artifact review**

```powershell
git diff --check
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify-phase3.ps1
git status --short
git diff --stat 64b09f508d9118a771195c4ab6449cc8487ab057..HEAD
git ls-files | rg "(^|/)(\.env|.*\.db|.*\.sqlite|node_modules|\.next|\.venv|__pycache__|objects?|data)(/|$)"
rg -n --hidden -g '!backend/uv.lock' -g '!web/pnpm-lock.yaml' "AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|Set-Cookie|Authorization:|postgresql[^\s]+:[^\s]+@" .
rg -n "55432|55000|deepaha-phase2-live-gate" infra/compose.phase3.yaml scripts/verify-phase3.ps1 .github/workflows/ci.yml
```

Review every match. The last command must have no Phase 3 verifier/compose match; existing historical Phase 1/2 files are outside that scoped command.

- [ ] **Step 6: Commit and push verifier/evidence**

```powershell
git add scripts/verify-phase3.ps1 .github/workflows/ci.yml docs/gates/phase-3 docs/development/README.md docs/development/system-roadmap.md README.md
git diff --cached --check
git commit -m "ci: verify phase 3 opportunity resolution"
git push
```

- [ ] **Step 7: Create stacked draft PR and inspect exact remote CI**

Use GitHub CLI only after confirming authentication and remote branch. Create a draft PR with base `phase-2-source-ingestion`, head `codex/phase-3-opportunity-resolution`, title prefixed `[STACKED][DRAFT]`, and body stating Phase 2 Gate OPEN, no merge, v0.3 PROPOSED, independent ports, verification commands and post-Gate rebase requirement.

```powershell
$phase3PrBody = @"
Phase 3 stacked candidate only. Phase 2 Gate remains OPEN.

- Do not merge or mark ready.
- v0.3 remains PROPOSED and the implementation status is IMPLEMENTED_PENDING_PHASE2_GATE.
- Local integration used only PostgreSQL 55433 and Moto 55001.
- Verification: scripts/verify.ps1 and scripts/verify-phase3.ps1.
- After Phase 2 closes, rebase onto its closing commit and rerun all verification before any promotion.
"@
gh pr create --draft --base phase-2-source-ingestion --head codex/phase-3-opportunity-resolution --title "[STACKED][DRAFT] Phase 3 opportunity resolution and versioning" --body $phase3PrBody
```

Inspect the exact head SHA and required job conclusions with `gh pr checks` and `gh run view`. Do not merge or mark ready for review.

- [ ] **Step 8: Update remote evidence only from actual results**

If every required job is `success`, update Phase 3 Gate docs with exact head SHA, run URL, job names and conclusions while retaining `BLOCKED_BY_PHASE2` and `IMPLEMENTED_PENDING_PHASE2_GATE`. Run `scripts/verify.ps1` and `scripts/verify-phase3.ps1` again after this docs-only change, then commit and push:

```powershell
git add docs/gates/phase-3
git diff --cached --check
git commit -m "docs: record phase 3 candidate verification"
git push
```

Wait for the docs commit CI and inspect it. If CI fails, use systematic debugging and keep the actual failed state in evidence until fixed.

---

## Final Verification Checklist

- [ ] Branch is `codex/phase-3-opportunity-resolution`, upstream matches, and worktree contains no unexpected changes.
- [ ] Base ancestry includes exact `64b09f508d9118a771195c4ab6449cc8487ab057` and no Phase 2 live worktree mutation.
- [ ] v0.1 and v0.2 Schema bytes and imports are unchanged.
- [ ] v0.3 Pydantic/JSON Schema/example/ORM/migration agree and remain PROPOSED.
- [ ] Migration `0001 -> 0002 -> 0003 -> 0002 -> 0003` passes when empty; downgrade refuses v0.3 data without deleting it.
- [ ] Resolver hard-links only official strong-key matches; weak/conflicting input is NEEDS_REVIEW.
- [ ] Stable public IDs are deterministic and never reused across merge/split/reversal.
- [ ]正文、附件、岗位表、更正、延期、取消 fixed cases resolve to the expected stable Opportunity.
- [ ] Field diffs, precedence, events and replay are deterministic; projection matches latest replay.
- [ ] merge/split/reversal action history is append-only and replayable.
- [ ] Default tests use no live site, browser or model.
- [ ] Phase 3 local services use only project `deepaha-phase3-*`, PostgreSQL 55433 and Moto 55001.
- [ ] `scripts/verify.ps1` and `scripts/verify-phase3.ps1` pass on the final tree.
- [ ] Scope/secret/artifact scans are reviewed; no prohibited files or data are tracked.
- [ ] Every Task commit is pushed; stacked PR remains draft and unmerged.
- [ ] Exact final head remote CI conclusions are inspected success before recording REMOTE_CI PASS.
- [ ] Gate docs say `BLOCKED_BY_PHASE2` / `IMPLEMENTED_PENDING_PHASE2_GATE`; Phase 3 Gate is not closed and v0.3 is not STABLE.
- [ ] Gate docs list the mandatory Phase 2 close-commit update, compatibility diff, empty/existing-data migration, full local/fresh/remote rerun and evidence refresh.

## Execution Handoff

This task has already selected Inline Execution because sub-agents are forbidden. Read this plan and its spec, use `superpowers:executing-plans`, execute Task 1 through Task 7 in order, update task checkboxes as work proceeds, and stop only for an actual external blocker or a safety boundary that has no in-scope alternative.
