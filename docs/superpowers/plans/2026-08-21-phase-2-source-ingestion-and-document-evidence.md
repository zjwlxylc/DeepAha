# DeepAha Phase 2 Source Ingestion and Document Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` task-by-task. Do not create sub-agents. Use `superpowers:test-driven-development` for behavior changes and `superpowers:verification-before-completion` before commits or completion claims.
>
> **Governance update (2026-08-22):** 本计划的工程实现已完成，Phase 2 Engineering Gate 已
> `CLOSED`；五轮 live、新鲜副本和最终候选 CI 继续作为 Release Qualification `IN_PROGRESS`。
> 下文历史步骤中的单一 “Gate OPEN/CLOSED” 应按此拆分解释，不得用于阻塞下游正常工程开发，
> 也不得据此把 v0.2 提前标记 `STABLE`。

**Goal:** Build a reproducible Phase 2 slice in which registered official endpoints produce auditable capture observations, immutable/deduplicated RawArtifacts, deterministic HTML/PDF/XLSX Documents, and replayable Evidence Locator v0.2 records.

**Architecture:** Extend stable v0.1 through a separate compatible v0.2 contract and Alembic expansion migration. A synchronous collector/CLI records every attempt and reuses Phase 1 object storage; format-specific parsers sit behind DeepAha types and never access the network. Default tests are offline; live source observation is explicit Gate evidence.

**Tech Stack:** Python 3.14, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL 18, boto3/Moto S3, httpx2 2.x, lxml 6.x, pypdf 6.x, openpyxl 3.x, defusedxml, pytest, Ruff, mypy, PowerShell, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-21-phase-2-source-ingestion-and-document-evidence-design.md`

## Global Constraints

- Work only in `D:\DeepAha\.worktrees\phase-2-source-ingestion` on `phase-2-source-ingestion`.
- Base is Phase 1 Gate commit `fb3dd924cc85c19cc8a13564cebc441f4d569521`; do not rewrite Phase 1 history.
- Preserve `contracts/schemas/v0.1.0/` byte-for-byte and keep v0.1 import paths working.
- Target contract `0.2.0` is `IMPLEMENTED`; it remains not `STABLE` until Phase 2 Release
  Qualification is `QUALIFIED`.
- Alembic is the only schema creation path; PostgreSQL must be `18.x`.
- Raw objects remain under `raw/sha256/...`; derived text uses `derived/documents/...`.
- Default tests/CI never access live sites, browsers or model APIs.
- Live checks require `DEEPAHA_ALLOW_LIVE_SOURCE_CHECK=true` and approved Endpoint policy.
- Do not add Redis, Celery, Valkey, pgvector, Playwright, Docling, OCR, LLM, Resolver, OpportunityVersion, rules, users, APIs or UI.
- Do not submit secrets, cookies, tokens, user data, DB/object files, caches, builds or unlicensed responses.

---

### Task 1: Add compatible v0.2 public contracts

**Files:**

- Create: `backend/src/deepaha/contracts/phase2.py`
- Modify: `backend/src/deepaha/contracts/export.py`
- Create: `backend/tests/contracts/test_phase2_contracts.py`
- Create: `contracts/examples/v0.2.0/phase-2-example.json`
- Create by exporter: `contracts/schemas/v0.2.0/{source,source-endpoint,capture-observation,raw-artifact,document,parse-attempt,opportunity,evidence-ref}.schema.json`

**Interfaces:** Produces `SourceEndpointSchema`, `CaptureObservationSchema`, `ParseAttemptSchema`, `OpportunitySchemaV02`, `EvidenceRefSchemaV02`, locator classes, `render_phase2_schemas()` and `write_phase2_schemas()`.

- [ ] **Step 1: Write RED contract tests**

```python
def test_v02_has_only_approved_opportunity_additions() -> None:
    legacy = {item.value for item in OpportunityType}
    assert {item.value for item in OpportunityTypeV02} - legacy == {
        "COMPETITION", "RESEARCH_PROGRAM", "SCHOLARSHIP",
        "YOUTH_DEVELOPMENT_PROGRAM",
    }

def test_capture_success_requires_artifact() -> None:
    values = observation_values(outcome="SUCCEEDED", artifact_id=None)
    with pytest.raises(ValidationError, match="SUCCEEDED"):
        CaptureObservationSchema.model_validate(values)

def test_v02_evidence_accepts_legacy_and_structured_locator() -> None:
    EvidenceRefSchemaV02.model_validate(evidence_values({"kind": "full_document", "value": "*"}))
    EvidenceRefSchemaV02.model_validate(evidence_values({
        "schema_version": "0.2.0", "kind": "html_selector",
        "selector": "main > p:nth-of-type(1)", "text_sha256": "1" * 64,
    }))
```

Also cover 304+Artifact invariants, FAILED error/artifact rules, Endpoint host/robots/licence rules, ParseAttempt states, PDF offsets, spreadsheet ranges, UTC, extra fields and v0.1 imports.

- [ ] **Step 2: Confirm RED**

```powershell
Set-Location backend
uv run pytest tests/contracts/test_phase2_contracts.py -v
```

Expected: missing `deepaha.contracts.phase2`.

- [ ] **Step 3: Implement exact v0.2 models**

Use `StrEnum`, `extra="forbid"`, model validators and a discriminated locator union:

```python
EvidenceLocatorV02 = Annotated[
    LegacyEvidenceLocator | HtmlSelectorLocator | PdfPageTextLocator | SpreadsheetRangeLocator,
    Field(discriminator="kind"),
]
```

New Opportunity enum retains all seven v0.1 values. Active Endpoint requires robots `ALLOWED|NOT_APPLICABLE`, non-UNKNOWN use basis, and URL host in normalized `allowed_hosts`.

- [ ] **Step 4: Export v0.2 without altering v0.1**

Add `PHASE2_SCHEMAS`; `write_phase2_schemas()` writes only `v0.2.0`. CLI option is `--version 0.1.0|0.2.0`; omitted keeps v0.1 behavior.

```powershell
uv run python -m deepaha.contracts.export .. --version 0.2.0
uv run pytest tests/contracts/test_phase1_contracts.py tests/contracts/test_phase2_contracts.py -v
```

The synthetic example uses `example.gov`, one successful observation/parse, internal unknown SCHOLARSHIP Opportunity and structured HTML locator; it asserts no business truth.

- [ ] **Step 5: Prove RED-GREEN and commit**

Temporarily remove `SCHOLARSHIP`, observe the additions test fail, restore, rerun green, then:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
Set-Location ..
git diff --check
git add backend/src/deepaha/contracts backend/tests/contracts/test_phase2_contracts.py contracts/examples/v0.2.0 contracts/schemas/v0.2.0
git commit -m "feat(contracts): define phase 2 observation schemas"
```

---

### Task 2: Add expansion migration and ORM models

**Files:**

- Create: `backend/migrations/versions/20260821_0002_phase2_observation_and_locators.py`
- Modify: `backend/src/deepaha/{sources,documents,opportunities}/models.py`
- Modify: `backend/src/deepaha/db/models.py`
- Modify: `backend/tests/integration/test_migrations.py`
- Create: `backend/tests/integration/test_phase2_persistence_contract.py`

**Interfaces:** Produces ORM `SourceEndpoint`, `CaptureObservation`, `ParseAttempt`, v0.2 EvidenceRef columns, expanded Opportunity CHECK and revision `20260821_0002`.

- [ ] **Step 1: Write RED persistence tests**

```python
def test_two_observations_can_reference_one_artifact(session: Session) -> None:
    endpoint, artifact = persist_endpoint_and_artifact(session)
    session.add_all([
        successful_observation(endpoint, artifact, run_id=uuid7()),
        successful_observation(endpoint, artifact, run_id=uuid7()),
    ])
    session.flush()
    assert session.scalar(select(func.count()).select_from(CaptureObservation)) == 2
```

Also assert tables/columns exist; FAILED+Artifact, 304 without Artifact, Endpoint/Source mismatch, ParseAttempt Document/Artifact mismatch and malformed locator shape are rejected; legacy locator remains valid; eleven Opportunity types pass and `GENERIC_JOB` fails.

- [ ] **Step 2: Confirm RED against PostgreSQL 18**

```powershell
docker compose -f infra/compose.yaml -p deepaha-phase2-db up -d --wait postgres s3
Set-Location backend
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_local_only@127.0.0.1:55432/deepaha"
uv run pytest tests/integration/test_migrations.py tests/integration/test_phase2_persistence_contract.py -m integration -v
```

- [ ] **Step 3: Implement models and migration**

Use JSONB for host/media arrays and locator payload. Fixed uniqueness:

```text
source_endpoints(source_id,url,policy_version)
capture_observations(collection_run_id,attempt_number)
parse_attempts(artifact_id,parser_name,parser_version)
```

Migration order: create three tables; add `locator_schema_version default '0.1.0'` and nullable JSONB payload; make legacy value nullable; replace locator CHECKs; replace Opportunity type CHECK. Downgrade refuses v0.2 data rather than deleting/rewriting it.

- [ ] **Step 4: Verify round-trip and metadata**

Extend isolated migration test to run `base -> 0001 -> 0002 -> 0001 -> 0002` and check tables per revision.

```powershell
uv run alembic upgrade head
uv run pytest tests/integration/test_migrations.py tests/integration/test_phase2_persistence_contract.py -m integration -v
uv run alembic check
```

- [ ] **Step 5: Prove constraint RED-GREEN and commit**

Temporarily allow 304 with null Artifact, confirm its test fails, restore/recreate disposable DB, rerun green, then:

```powershell
Set-Location ..
docker compose -f infra/compose.yaml -p deepaha-phase2-db down --remove-orphans
git add backend/migrations/versions/20260821_0002_phase2_observation_and_locators.py backend/src/deepaha/sources/models.py backend/src/deepaha/documents/models.py backend/src/deepaha/opportunities/models.py backend/src/deepaha/db/models.py backend/tests/integration/test_migrations.py backend/tests/integration/test_phase2_persistence_contract.py
git commit -m "feat(db): persist phase 2 capture observations"
```

---

### Task 3: Implement the versioned Source Registry

**Files:**

- Create: `backend/src/deepaha/sources/registry.py`
- Create: `backend/tests/sources/test_registry_manifest.py`
- Create: `backend/tests/integration/test_source_registry.py`
- Create: `backend/tests/fixtures/sources/{registry-valid,registry-invalid}.json`
- Create: `config/sources/phase2-official-endpoints.json`
- Create: `config/sources/README.md`

**Interfaces:** Produces `SourceRegistryManifest`, `RegistryImportResult`, `load_registry_manifest()` and `import_registry()`.

- [ ] **Step 1: Write RED tests**

```python
def test_registry_import_is_idempotent(session: Session, manifest: SourceRegistryManifest) -> None:
    assert import_registry(session, manifest).created_endpoints == 1
    assert import_registry(session, manifest).created_endpoints == 0

def test_changed_meaning_under_same_policy_version_fails(session: Session, manifest) -> None:
    import_registry(session, manifest)
    with pytest.raises(SourcePolicyConflict, match="SOURCE_POLICY_CONFLICT"):
        import_registry(session, change_timeout(manifest, 61))
```

Unit tests reject BOM/non-object JSON, unknown fields, duplicates, active UNKNOWN/DISALLOWED robots, OPEN_LICENSE without name/URL, fixture permission for LINK_ONLY and URL outside allowed hosts.

- [ ] **Step 2: Confirm RED**

```powershell
docker compose -f infra/compose.yaml -p deepaha-phase2-registry up -d --wait postgres s3
Set-Location backend
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_local_only@127.0.0.1:55432/deepaha"
uv run pytest tests/sources/test_registry_manifest.py tests/integration/test_source_registry.py -v
```

- [ ] **Step 3: Implement strict loading/import**

Manifest has literal `schema_version="0.2.0"`; loading never expands environment values. Import never commits. Replays return exact rows; changed meaning under `(source_id,url,policy_version)` raises conflict.

- [ ] **Step 4: Add exactly ten official policy candidates**

Roles/official hosts are fixed: 国家公务员局 `scs.gov.cn`; 人社部招聘 `mohrss.gov.cn`; 国资委招聘 `sasac.gov.cn`; 中国政府网政策 `gov.cn`; 教育部资助 `moe.gov.cn`; 共青团青年发展 `gqt.org.cn`; 浙江人社 `rlsbt.zj.gov.cn`; 浙江人事考试 `zjks.com`; 浙江科技 `kjt.zj.gov.cn`; 浙江教育 `jyt.zj.gov.cn`.

Open each current official list page and robots/terms page; record actual URL, redirect hosts, verification time, robots decision, use basis and note. Use `fixture_storage_allowed=false` unless an explicit licence permits storage. An invalid host may only be replaced by the same authority's current official host with evidence in README.

- [ ] **Step 5: Verify and commit**

```powershell
uv run pytest tests/sources/test_registry_manifest.py -v
uv run pytest tests/integration/test_source_registry.py -m integration -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
Set-Location ..
docker compose -f infra/compose.yaml -p deepaha-phase2-registry down --remove-orphans
git add backend/src/deepaha/sources/registry.py backend/tests/sources backend/tests/integration/test_source_registry.py backend/tests/fixtures/sources config/sources
git commit -m "feat(sources): add versioned official source registry"
```

---

### Task 4: Collect HTTP evidence with independent observations

**Files:**

- Modify with uv: `backend/{pyproject.toml,uv.lock}`
- Create: `backend/src/deepaha/artifacts/observed.py`
- Create: `backend/src/deepaha/sources/{transport,collector}.py`
- Create: `backend/tests/sources/test_collector_policy.py`
- Create: `backend/tests/integration/test_collection_service.py`

**Interfaces:** Produces `HttpRequest`, `HttpResponse`, `HttpTransport`, `HostResolver`, `Clock`, `Sleeper`, `HttpxTransport`, `CollectionRunner`, `CollectionRunResult`, `import_observed_raw_artifact()`.

- [ ] **Step 1: Move httpx2 to runtime and verify**

```powershell
Set-Location backend
uv remove --group dev httpx2
uv add "httpx2>=2.12,<3"
uv lock --check
uv run python -c "import httpx2; print(httpx2.__version__)"
```

- [ ] **Step 2: Write RED policy/retry tests**

```python
def test_retry_records_every_attempt() -> None:
    result = run_scripted([timeout(), response(503), response(200, b"official")])
    assert [x.outcome for x in result.attempts] == ["FAILED", "FAILED", "SUCCEEDED"]
    assert result.sleeps == [1, 2]

def test_unapproved_redirect_stops_before_follow() -> None:
    transport = ScriptedTransport([redirect("https://evil.example/file")])
    result = run_with(transport, allowed_hosts=("official.example",))
    assert result.final_error_code == "REDIRECT_HOST_NOT_ALLOWED"
    assert len(transport.requests) == 1
```

Cover inactive/robots/use policy, literal/resolved private IP, rate interval, valid/invalid 304, empty/oversize/media mismatch, 429/5xx exhaustion and permanent 404. Fake Sleeper never sleeps.

- [ ] **Step 3: Write RED integration semantics**

```python
def test_same_bytes_create_two_observations_one_artifact(runner, session_factory) -> None:
    runner.collect(ENDPOINT_ID)
    runner.clock.advance(hours=6)
    runner.collect(ENDPOINT_ID)
    with session_factory() as session:
        rows = session.scalars(select(CaptureObservation)).all()
        assert len(rows) == 2
        assert rows[0].artifact_id == rows[1].artifact_id
        assert session.scalar(select(func.count()).select_from(RawArtifact)) == 1
```

Also assert final failure persists all failed attempts and creates no Artifact; 304 references the previous Artifact.

- [ ] **Step 4: Confirm RED with local services**

```powershell
docker compose -f infra/compose.yaml -p deepaha-phase2-collect up -d --wait postgres s3
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_local_only@127.0.0.1:55432/deepaha"
$env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55000"
$env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
$env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
$env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "phase2-local"
$env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "phase2-local-secret"
uv run pytest tests/sources/test_collector_policy.py tests/integration/test_collection_service.py -v
```

- [ ] **Step 5: Implement observed import without weakening Phase 1**

Keep `import_raw_artifact()` and Phase 1 conflict tests unchanged. New function has exact signature:

```python
def import_observed_raw_artifact(
    *, session: Session, object_store: ObjectStore, command: ImportRawArtifactCommand
) -> ObservedRawArtifactResult: ...
```

It shares validation/hash/object integrity helpers, but an existing `(source_id,content_sha256)` is returned regardless of new observation metadata; the new metadata lives in CaptureObservation.

- [ ] **Step 6: Implement transport and runner**

`HttpxTransport.get_once()` uses `Client(follow_redirects=False, trust_env=False)` and streaming, keeps only status/final URL/Content-Type/ETag/Last-Modified/Location/body, and rejects >`25_000_000` bytes. Resolve every host; reject private, loopback, link-local, multicast, reserved and unspecified IP. Validate each redirect.

`CollectionRunner` receives a sessionmaker. Each policy failure/HTTP attempt uses its own transaction and one observation. Expected failures return a result. Retry delays are exactly 1,2 seconds. Valid 2xx stores/reuses Artifact; 304 queries the latest successful Artifact.

- [ ] **Step 7: Verify Phase 1 and Phase 2 together, then commit**

```powershell
uv run pytest tests/integration/test_raw_artifact_import.py tests/integration/test_collection_service.py -m integration -v
uv run pytest tests/sources/test_collector_policy.py -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
Set-Location ..
docker compose -f infra/compose.yaml -p deepaha-phase2-collect down --remove-orphans
git diff --check
git add backend/pyproject.toml backend/uv.lock backend/src/deepaha/artifacts/observed.py backend/src/deepaha/sources/transport.py backend/src/deepaha/sources/collector.py backend/tests/sources/test_collector_policy.py backend/tests/integration/test_collection_service.py
git commit -m "feat(sources): collect immutable evidence with observations"
```

---

### Task 5: Add source health and explicit CLI

**Files:**

- Modify: `backend/src/deepaha/core/settings.py`
- Create: `backend/src/deepaha/sources/{health,cli}.py`
- Create: `backend/tests/sources/{test_health,test_cli}.py`
- Create: `backend/tests/integration/test_source_health.py`

**Interfaces:** Produces `SourceHealthSummary`, `get_source_health()` and CLI `import-registry`, `collect`, `collect-manifest`, `health`.

- [ ] **Step 1: Write RED aggregation/permission tests**

```python
def test_health_is_derived_from_observations(session: Session) -> None:
    endpoint = add_observations(session, ["SUCCEEDED", "FAILED", "FAILED"])
    value = get_source_health(session, endpoint.endpoint_id, AS_OF)
    assert (value.attempts_24h, value.successes_24h, value.consecutive_failures) == (3, 1, 2)

def test_collect_requires_explicit_live_permission(monkeypatch) -> None:
    monkeypatch.delenv("DEEPAHA_ALLOW_LIVE_SOURCE_CHECK", raising=False)
    assert main(["collect", "--endpoint-id", str(ENDPOINT_ID)]) == 2
```

Assert 304 is valid without replacing last Artifact; >24h rows are excluded; import/health do not need live permission; output never contains credentials/body.

- [ ] **Step 2: Confirm RED and implement**

```powershell
Set-Location backend
uv run pytest tests/sources/test_health.py tests/sources/test_cli.py tests/integration/test_source_health.py -v
```

Add strict `allow_live_source_check: bool=False` (`DEEPAHA_ALLOW_LIVE_SOURCE_CHECK`). Use standard argparse; `main(argv)->int`. Live permission never bypasses Endpoint policy. Output UTF-8 JSON IDs/outcomes/codes/counts only.

- [ ] **Step 3: Verify and commit**

```powershell
uv run pytest tests/sources/test_health.py tests/sources/test_cli.py -v
uv run pytest tests/integration/test_source_health.py -m integration -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
Set-Location ..
git add backend/src/deepaha/core/settings.py backend/src/deepaha/sources/health.py backend/src/deepaha/sources/cli.py backend/tests/sources/test_health.py backend/tests/sources/test_cli.py backend/tests/integration/test_source_health.py
git commit -m "feat(sources): expose auditable collection health"
```

---

### Task 6: Add parser protocol and persistence service

**Files:**

- Create: `backend/src/deepaha/documents/{parser,normalization,service}.py`
- Create: `backend/tests/documents/{test_normalization,test_parser_service}.py`
- Create: `backend/tests/integration/test_document_service.py`

**Interfaces:** Produces `DocumentParser`, `ParsedDocument`, `ParseDocumentCommand/Result`, `DocumentService`, `normalize_text()`, `build_derived_text_key()`.

- [ ] **Step 1: Write RED normalization/service tests**

```python
def test_normalize_text_is_conservative() -> None:
    assert normalize_text("标题  \r\n\r\n\r\n日期：2026-08-21\t \r\n") == "标题\n\n日期：2026-08-21\n"

def test_derived_key_never_uses_raw_namespace() -> None:
    assert build_derived_text_key("a"*64, "html_lxml", "0.2.0") == (
        f"derived/documents/{'a'*64}/html_lxml/0.2.0/text.txt"
    )
```

Fake-parser tests assert success stores derived bytes+Document+EvidenceRefs+ParseAttempt; replay returns same Document; new parser version creates a new one; expected failure stores FAILED without Document; review reason stores NEEDS_REVIEW; conflicting derived bytes never overwrite.

- [ ] **Step 2: Confirm RED with PostgreSQL/S3**

```powershell
docker compose -f infra/compose.yaml -p deepaha-phase2-document up -d --wait postgres s3
Set-Location backend
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_local_only@127.0.0.1:55432/deepaha"
$env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55000"
$env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
$env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
$env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "phase2-local"
$env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "phase2-local-secret"
uv run pytest tests/documents/test_normalization.py tests/documents/test_parser_service.py tests/integration/test_document_service.py -v
```

- [ ] **Step 3: Implement small DeepAha types**

```python
@dataclass(frozen=True, slots=True)
class ParsedDocument:
    title: str | None
    published_at: datetime | None
    language: str
    normalized_text: str
    locators: tuple[EvidenceLocatorV02, ...]
    needs_review_reasons: tuple[str, ...]

class DocumentParser(Protocol):
    name: str
    version: str
    def supports(self, media_type: str) -> bool: ...
    def parse(self, content: bytes, *, artifact_sha256: str) -> ParsedDocument: ...
```

Parser never receives URL/session/store/Opportunity. Service loads Artifact bytes, selects exactly one parser, revalidates locators, uses put-if-absent derived key, and persists in one transaction. Expected parse errors become stable attempts; programmer errors raise.

- [ ] **Step 4: Verify raw immutability and commit**

Integration test compares raw bytes/hash/key before and after parse and proves derived key differs.

```powershell
uv run pytest tests/documents/test_normalization.py tests/documents/test_parser_service.py -v
uv run pytest tests/integration/test_document_service.py -m integration -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
Set-Location ..
docker compose -f infra/compose.yaml -p deepaha-phase2-document down --remove-orphans
git add backend/src/deepaha/documents/parser.py backend/src/deepaha/documents/normalization.py backend/src/deepaha/documents/service.py backend/tests/documents backend/tests/integration/test_document_service.py
git commit -m "feat(documents): persist versioned parse evidence"
```

---

### Task 7: Parse HTML with replayable locators

**Files:**

- Modify with uv: `backend/{pyproject.toml,uv.lock}`
- Create: `backend/src/deepaha/documents/{html,locator}.py`
- Create: `backend/tests/documents/{test_html_parser,test_locator_replay}.py`
- Create: `backend/tests/fixtures/documents/{minimal-official,empty-body}.html`

- [ ] **Step 1: Add dependency and write RED tests**

```powershell
Set-Location backend
uv add "lxml[cssselect]>=6.1,<7"
uv run python -c "import lxml, cssselect; print(lxml.__version__)"
```

Fixture contains `zh-CN`, title, main/article, two paragraphs and excluded script/style. Assert exact normalized text, stable selectors/hashes, body fallback, invalid language -> `und`, blank -> `HTML_TEXT_EMPTY`, deterministic malformed recovery and no external network/entity.

```python
def test_html_locators_replay_hash() -> None:
    content = FIXTURE.read_bytes()
    parsed = LxmlHtmlParser().parse(content, artifact_sha256=sha256(content).hexdigest())
    for locator in parsed.locators:
        text = replay_html_locator(content, locator)
        assert sha256(text.encode()).hexdigest() == locator.text_sha256
```

- [ ] **Step 2: Confirm RED and implement**

```powershell
uv run pytest tests/documents/test_html_parser.py tests/documents/test_locator_replay.py -v
```

Configure lxml `no_network=True`, `resolve_entities=False`, `recover=True`, `huge_tree=False`. Root priority: single main, single article, body. Remove script/style/noscript/template. Generate selectors from tags+`:nth-of-type`, not page classes/IDs. Title only from `<title>`, language only valid `html[lang]`, published_at remains null.

- [ ] **Step 3: Prove RED-GREEN and commit**

Temporarily include script text, observe failure, restore, then:

```powershell
uv run pytest tests/documents/test_html_parser.py tests/documents/test_locator_replay.py -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
Set-Location ..
git add backend/pyproject.toml backend/uv.lock backend/src/deepaha/documents/html.py backend/src/deepaha/documents/locator.py backend/tests/documents/test_html_parser.py backend/tests/documents/test_locator_replay.py backend/tests/fixtures/documents
git commit -m "feat(documents): parse HTML with replayable evidence"
```

---

### Task 8: Parse text PDFs by page evidence

**Files:**

- Modify with uv: `backend/{pyproject.toml,uv.lock}`
- Create: `backend/src/deepaha/documents/pdf.py`
- Modify: `backend/src/deepaha/documents/locator.py`
- Create: `backend/tests/documents/test_pdf_parser.py`
- Modify: `backend/tests/documents/test_locator_replay.py`
- Create: `backend/tests/fixtures/documents/generate_fixtures.py`
- Create from generator: `backend/tests/fixtures/documents/{minimal-text,empty-text}.pdf`
- Create: `backend/tests/fixtures/documents/pdf-fixtures.manifest.json`

- [ ] **Step 1: Add pypdf and deterministic fixtures**

```powershell
Set-Location backend
uv add "pypdf>=6.16,<7"
uv run python -c "import pypdf; print(pypdf.__version__)"
```

Generator uses standard library to write fixed PDF 1.4 objects/xref with Helvetica and two ASCII text pages; a second run in another temp directory must be byte-equal. Manifest records exact SHA/size, `synthetic=true`, no business facts.

- [ ] **Step 2: Write/confirm RED tests**

```python
def test_pdf_locator_replays_page_text() -> None:
    content = TEXT_PDF.read_bytes()
    parsed = PypdfDocumentParser().parse(content, artifact_sha256=sha256(content).hexdigest())
    assert {x.page_number for x in parsed.locators} == {1, 2}
    for locator in parsed.locators:
        assert sha256(replay_pdf_locator(content, locator).encode()).hexdigest() == locator.text_sha256
```

Cover encrypted, damaged, >500 pages, all-empty, partially empty. Expected codes: `PDF_ENCRYPTED`, `PDF_PARSE_FAILED`, `PDF_PAGE_LIMIT_EXCEEDED`, `PDF_TEXT_EMPTY`, `PDF_PAGE_TEXT_MISSING`.

```powershell
uv run pytest tests/documents/test_pdf_parser.py tests/documents/test_locator_replay.py -v
```

- [ ] **Step 3: Implement minimal pypdf adapter**

Use `PdfReader(BytesIO(content), strict=True)`, reject encryption, extract each page separately, join pages with `\n\f\n`. Locator page is 1-based; offsets are page-local normalized text. Set title/published_at null and language `und`; no OCR/metadata inference.

- [ ] **Step 4: Prove RED-GREEN and commit**

Temporarily make pages zero-based, observe test failure, restore, then:

```powershell
uv run pytest tests/documents/test_pdf_parser.py tests/documents/test_locator_replay.py -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
Set-Location ..
git add backend/pyproject.toml backend/uv.lock backend/src/deepaha/documents/pdf.py backend/src/deepaha/documents/locator.py backend/tests/documents/test_pdf_parser.py backend/tests/documents/test_locator_replay.py backend/tests/fixtures/documents
git commit -m "feat(documents): parse text PDFs by page evidence"
```

---

### Task 9: Parse XLSX with safe cell evidence

**Files:**

- Modify with uv: `backend/{pyproject.toml,uv.lock}`
- Create: `backend/src/deepaha/documents/spreadsheet.py`
- Modify: `backend/src/deepaha/documents/locator.py`
- Create: `backend/tests/documents/test_spreadsheet_parser.py`
- Modify: `backend/tests/documents/test_locator_replay.py`
- Modify: `backend/tests/fixtures/documents/generate_fixtures.py`
- Create from generator: `backend/tests/fixtures/documents/minimal-table.xlsx`
- Create: `backend/tests/fixtures/documents/xlsx-fixtures.manifest.json`

- [ ] **Step 1: Add dependencies and deterministic fixture**

```powershell
Set-Location backend
uv add "openpyxl>=3.1.5,<4" "defusedxml>=0.7,<1"
uv run python -c "import openpyxl, defusedxml; print(openpyxl.__version__)"
```

Generator fixes workbook created/modified time, rewrites ZIP entries sorted with timestamp `(1980,1,1,0,0,0)`, and proves two outputs equal. Workbook has sheets `岗位表`/`说明`, strings, integer, ISO date string and formula string. Manifest records exact SHA/size and no macro/external links/business facts.

- [ ] **Step 2: Write/confirm RED tests**

```python
def test_xlsx_locator_replays_cells() -> None:
    content = XLSX.read_bytes()
    parsed = OpenpyxlSpreadsheetParser().parse(content, artifact_sha256=sha256(content).hexdigest())
    for locator in parsed.locators:
        assert hash_normalized_cells(replay_spreadsheet_locator(content, locator)) == locator.cells_sha256
```

Cover empty, xlsm/macro, >10,000 ZIP entries, >100,000,000 uncompressed bytes, path traversal, external link, formula preserved/not evaluated, 1-based coordinates and merged cells.

```powershell
uv run pytest tests/documents/test_spreadsheet_parser.py tests/documents/test_locator_replay.py -v
```

- [ ] **Step 3: Implement archive preflight and parser**

Reject unsafe ZIP metadata and `vbaProject.bin`; load only:

```python
load_workbook(BytesIO(content), read_only=True, data_only=False, keep_links=False)
```

One locator per non-empty row, first-to-last non-empty column. Hash compact UTF-8 JSON ordered by row/column with normalized string value. Keep leading `=` formulas; never execute formulas/macros/links.

- [ ] **Step 4: Prove RED-GREEN and commit**

Temporarily set `data_only=True`, observe formula failure, restore, then:

```powershell
uv run pytest tests/documents/test_spreadsheet_parser.py tests/documents/test_locator_replay.py -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
Set-Location ..
git add backend/pyproject.toml backend/uv.lock backend/src/deepaha/documents/spreadsheet.py backend/src/deepaha/documents/locator.py backend/tests/documents/test_spreadsheet_parser.py backend/tests/documents/test_locator_replay.py backend/tests/fixtures/documents
git commit -m "feat(documents): parse XLSX with cell evidence"
```

---

### Task 10: Add licensed official HTML vertical slice and live runner

**Files:**

- Create: `backend/tests/fixtures/official/civil-service-fast-stream-news-2025.html`
- Create: `backend/tests/fixtures/official/civil-service-fast-stream-news-2025-html.manifest.json`
- Modify: `backend/tests/fixtures/official/README.md`
- Create: `backend/tests/integration/test_phase2_official_html_sample.py`
- Create: `backend/tests/sources/test_official_source_manifest.py`
- Create: `scripts/run-phase2-source-observation.ps1`
- Create: `docs/gates/phase-2/source-observation-template.md`

- [ ] **Step 1: Write RED identity/licence and vertical tests**

```python
def test_official_html_matches_manifest_and_ogl() -> None:
    content = HTML.read_bytes()
    manifest = json.loads(MANIFEST.read_text("utf-8"))
    assert len(content) == manifest["byte_size"]
    assert sha256(content).hexdigest() == manifest["content_sha256"]
    assert manifest["license"]["name"] == "Open Government Licence v3.0"
    assert manifest["limitations"] == {
        "gold_business_sample": False,
        "china_launch_coverage": False,
        "current_application_status_proven": False,
    }
```

Vertical integration requires one Source/Endpoint/Observation/RawArtifact/Document/ParseAttempt, replayable HTML EvidenceRefs, zero Opportunity rows and unchanged raw bytes.

- [ ] **Step 2: Capture only the exact official response**

URL is `https://www.gov.uk/government/news/civil-service-fast-stream-named-uks-top-graduate-employer`. Open current GOV.UK terms, capture only HTML response (no external assets/cookies/headers), calculate actual time/status/media/size/SHA, and put literal values/OGL attribution in manifest. If page or licence no longer qualifies, keep Gate open; never substitute handwritten HTML.

- [ ] **Step 3: Implement bounded live runner**

PowerShell script requires live permission; accepts `-Rounds` 1..5, `-IntervalSeconds` default 21600 and caller output path outside repo; refuses interval below active policy; runs sequentially; persists partial observations on interruption; outputs only endpoint IDs/URLs, times, status/outcome/error/artifact hash/key and counts; never response bodies or credentials. Unit test mocks CLI and never sleeps/network.

- [ ] **Step 4: Verify and commit without Chinese response bytes**

```powershell
docker compose -f infra/compose.yaml -p deepaha-phase2-official up -d --wait postgres s3
Set-Location backend
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_local_only@127.0.0.1:55432/deepaha"
$env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55000"
$env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
$env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
$env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "phase2-local"
$env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "phase2-local-secret"
uv run pytest tests/sources/test_official_source_manifest.py -v
uv run pytest tests/integration/test_phase2_official_html_sample.py -m integration -v
Set-Location ..
docker compose -f infra/compose.yaml -p deepaha-phase2-official down --remove-orphans
git add backend/tests/fixtures/official backend/tests/integration/test_phase2_official_html_sample.py backend/tests/sources/test_official_source_manifest.py scripts/run-phase2-source-observation.ps1 docs/gates/phase-2/source-observation-template.md
git commit -m "test(phase2): add licensed official HTML evidence"
```

---

### Task 11: Verify, run and honestly close or retain the Phase 2 Gate

**Files:**

- Modify: `backend/pyproject.toml`
- Create: `scripts/verify-phase2.ps1`
- Modify: `.github/workflows/ci.yml`
- Create: `docs/gates/phase-2/{README,acceptance-results,test-summary,source-observation-summary,parser-evaluation-summary,sample-provenance,security-and-compliance,operations,deferred-decisions}.md`
- Modify only from actual evidence: `docs/development/{domain-contracts-v0.2,README}.md`, `README.md`

- [ ] **Step 1: Keep tests offline by marker**

```toml
addopts = "-q -m 'not integration and not live_source'"
markers = [
  "integration: requires PostgreSQL 18 and the local S3 endpoint",
  "live_source: requires explicitly enabled network access to approved official endpoints",
]
```

- [ ] **Step 2: Write scoped `verify-phase2.ps1`**

Follow Phase 1 structure with compose project `deepaha-phase2-$PID`: run `verify.ps1`; start only scoped postgres/S3; locked sync; Alembic upgrade; integration tests; source/document/contract offline tests; `alembic check`; scoped cleanup in `finally`, no `-v`, deletion or live permission.

- [ ] **Step 3: Prove verifier RED-GREEN**

Change one expected official/locator hash; confirm non-zero; restore and confirm:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-phase2.ps1
```

- [ ] **Step 4: Add matching CI**

Extend existing integration or add `phase2-contract-and-parser` with Python 3.14, locked deps, PostgreSQL 18.4, Moto 5.2.2, migration, all integration tests, offline parser/contracts and `alembic check`. Never set live permission. Only add workflow_dispatch live job if real secret/runner policy exists; otherwise defer it explicitly.

- [ ] **Step 5: Create truthful split Gate evidence**

Record implementation, Engineering Gate, Release Qualification and contract maturity separately. Before
live/fresh/final-remote success, Release Qualification remains `IN_PROGRESS` and v0.2 remains not
`STABLE`. Populate only actual commands, versions, counts, hashes and failures; never planned values.

- [ ] **Step 6: Run the five-round live window**

Use disposable DB/S3 outside repo:

```powershell
$env:DEEPAHA_ALLOW_LIVE_SOURCE_CHECK = "true"
$phase2ObservationOutput = Join-Path ([System.IO.Path]::GetTempPath()) "deepaha-phase2-observation-$([guid]::NewGuid().ToString('N')).json"
powershell -ExecutionPolicy Bypass -File scripts/run-phase2-source-observation.ps1 -Rounds 5 -IntervalSeconds 21600 -OutputPath $phase2ObservationOutput
```

Rounds span at least 24h. Export only summaries and manual maintenance minutes. If final
`SUCCEEDED+NOT_MODIFIED` ratio <98%, policy is violated, or one site forces a generic-code workaround,
Release Qualification becomes `FAILED` or `BLOCKED`; only a real engineering defect triggers Engineering
Gate re-evaluation.

- [ ] **Step 7: Full and fresh-copy verification**

```powershell
git diff --check
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify-phase1.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify-phase2.ps1
```

Repeat in a temporary clone of exact candidate commit without copying environments/caches/data. Record path, commit, runtime/container versions, exit codes and counts.

- [ ] **Step 8: Scope/secret/artifact review**

```powershell
git status --short
git diff --check
git diff --stat fb3dd924cc85c19cc8a13564cebc441f4d569521..HEAD
git ls-files | rg "(^|/)(\.env|.*\.db|.*\.sqlite|node_modules|\.next|\.venv|__pycache__|objects?|data)(/|$)"
rg -n --hidden -g '!backend/uv.lock' -g '!web/pnpm-lock.yaml' "AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|postgresql[^\s]+:[^\s]+@|Set-Cookie|Authorization:" .
```

Review every match; only labelled disposable local constants are allowed.

- [ ] **Step 9: Commit OPEN evidence, push, inspect CI**

```powershell
git add backend/pyproject.toml backend/uv.lock scripts/verify-phase2.ps1 .github/workflows/ci.yml docs/gates/phase-2 docs/development/README.md README.md
git commit -m "ci: verify phase 2 evidence pipeline"
git push -u origin phase-2-source-ingestion
```

Do not claim remote success until required job conclusions are inspected.

- [ ] **Step 10: Qualify release only with every real proof**

Engineering Gate closes when implementation, contracts, migrations, tests, security, review and scope evidence
meet their exits. Only when fresh-copy, live-window and final-candidate remote CI also meet all applicable
release exits may Release Qualification become `QUALIFIED` and v0.2 become `STABLE`. Otherwise keep
Release Qualification `IN_PROGRESS`, `FAILED` or `BLOCKED`, report the exact gap, and do not use that gap
to block Phase 3 normal engineering development.

---

## Final Verification Checklist

- [ ] Clean expected Git state and `git diff --check` exit 0.
- [ ] v0.1 Schema bytes unchanged; v0.2 Schema/example/Pydantic/ORM/migration agree.
- [ ] Migration `0001 -> 0002 -> 0001 -> 0002` and `alembic check` pass.
- [ ] Phase 1 provenance tests still pass.
- [ ] Same content gives two observations/one Artifact; failure gives observation/no Artifact; 304 references existing Artifact.
- [ ] HTML/PDF/XLSX fixture text hashes and locators replay deterministically.
- [ ] Raw bytes/metadata remain unchanged after parse; unsafe files have audited failure.
- [ ] Default tests use no live site/browser/model.
- [ ] Ten Endpoint policies have robots/use evidence and no unknowns.
- [ ] Five live rounds span >=24h and satisfy Release Qualification, or its non-qualified state remains explicit.
- [ ] `verify.ps1`, `verify-phase1.ps1`, `verify-phase2.ps1` pass locally/fresh before completion claim.
- [ ] Required remote CI conclusions are inspected success for the claimed commit.
- [ ] No Phase 3/infrastructure/model/user/UI expansion or prohibited artifact is tracked.
- [ ] Gate docs separate plan, implementation and verification.

## Execution Handoff

In a new Codex task, open `D:\DeepAha\.worktrees\phase-2-source-ingestion`, read `AGENTS.md`, the Blueprint v1.2 reconciliation, Phase 2 spec and this plan completely, then use `superpowers:executing-plans`. Execute Task 1 onward in order without sub-agents. Stop only for external policy/licence blockage, a failing clean baseline, or an action crossing the explicit Phase 2 boundary.
