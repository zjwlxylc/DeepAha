# DeepAha Phase 1 领域契约与原始证据实施计划

> **给实施 Agent：** 必须使用 `superpowers:executing-plans`，按 Task 执行，并在每个 Task 后设置复核点。用户明确禁止子 Agent，不得委派。使用下方复选框跟踪每一步。

**目标：** 实现 Phase 1 v0.1 领域契约，以及由 PostgreSQL 18 和 S3 兼容本地服务支撑的可复现、不可变原始证据纵向切片。

**架构：** Pydantic v2 模型作为五个入库 JSON Schema 的作者源。SQLAlchemy 2 模型和 Alembic 迁移把同一契约持久化到 PostgreSQL 18.4；`boto3` 适配器把内容寻址字节写入 S3，Moto 5.2.2 提供本地/CI 端点。固定的 OGL v3.0 GOV.UK JSON 响应用于证明哈希重放、RawArtifact 幂等导入、证据配对，以及 Document 与 Opportunity 的分离。

**技术栈：** Python 3.14、Pydantic v2、jsonschema、SQLAlchemy 2.x、Alembic、Psycopg 3、PostgreSQL 18.4、boto3、boto3-stubs、Moto 5.2.2、pytest、Ruff、mypy、Docker Compose、GitHub Actions。

**设计规范（Spec）：** `docs/superpowers/specs/2026-08-21-phase-1-domain-contract-and-raw-evidence-design.md`

## 实施前置条件

用户明确确认 spec 中 D1-D7 之前，不得执行本计划。如果用户调整任何决策，必须先同步修订 spec 和本计划，再编写实现代码。

实施启动时先使用 `superpowers:using-git-worktrees` 检测当前工作区。除非用户明确授权直接修改 `main`，推荐从已核验基线创建 `phase-1-domain-evidence` 分支并在隔离 worktree 中执行；创建 worktree 前必须单独取得用户同意。任何新出现的用户自有改动都只读盘点，不移动、不提交、不覆盖。

## 全局约束

- 从 `main` 的 `22f11b8e99311067670d8bbf1394fb881bf7e872` 开始；如果出现更新的用户自有变更，先在不丢弃它们的前提下协调。
- 使用 `superpowers:test-driven-development`：观察到失败测试之前，不写对应生产行为。
- 使用 `superpowers:verification-before-completion`：没有新鲜命令输出，不声称通过或完成。
- Phase 1 严格限定在 Source、RawArtifact、Document、Opportunity、EvidenceRef、PostgreSQL、迁移、S3 兼容原始存储、一个固定样本和 Gate 证据。
- 不增加实时采集器、通用解析器、OpportunityVersion、LLM、规则、资格、排序、用户、Redis、向量、Worker、队列、生产云基础设施或 UI。
- 使用 PostgreSQL `18.4-alpine3.23` 和 Moto `5.2.2`；不得静默改变大版本。
- 默认测试不得访问官方样本 URL。
- 不提交秘密、真实用户数据、数据库文件、对象存储内容、容器卷、缓存或构建产物。
- `RawArtifact` 字节不可变。解析或派生数据永远不使用原始对象键。
- `Document` 与 `Opportunity` 保持独立契约、ORM 类、表、ID、标题和生命周期。
- 新鲜本地验证及所需远程 CI 均取得真实成功证据之前，Phase 1 Gate 保持 `OPEN`。

---

## 文件地图

### 契约作者源与发布物

- Add `docs/superpowers/specs/2026-08-21-phase-1-domain-contract-and-raw-evidence-design.md` — approved Phase 1 design baseline.
- Add `docs/superpowers/plans/2026-08-21-phase-1-domain-contract-and-raw-evidence.md` — this executable plan.
- Create `backend/src/deepaha/contracts/__init__.py` — public exports for Phase 1 contracts.
- Create `backend/src/deepaha/contracts/common.py` — UUIDv7, UTC, SHA-256, public ID, URL and S3 URI types.
- Create `backend/src/deepaha/contracts/phase1.py` — enums and five Pydantic contracts.
- Create `backend/src/deepaha/contracts/export.py` — deterministic JSON Schema renderer and CLI.
- Create `contracts/schemas/v0.1.0/source.schema.json`.
- Create `contracts/schemas/v0.1.0/raw-artifact.schema.json`.
- Create `contracts/schemas/v0.1.0/document.schema.json`.
- Create `contracts/schemas/v0.1.0/opportunity.schema.json`.
- Create `contracts/schemas/v0.1.0/evidence-ref.schema.json`.
- Create `contracts/examples/v0.1.0/phase-1-official-sample.json`.
- Create `backend/tests/contracts/test_phase1_contracts.py`.
- Modify `docs/development/domain-contracts-v0.1.md` — record only approved D1-D5 semantics.

### 数据库与持久化

- Modify `backend/pyproject.toml` and `backend/uv.lock` — direct runtime/dev dependencies and pytest marker policy.
- Modify `backend/src/deepaha/core/settings.py` — database and object-store settings.
- Modify `backend/tests/core/test_settings.py` — prefixed settings and secret representation.
- Create `backend/alembic.ini`.
- Create `backend/migrations/env.py`.
- Create `backend/migrations/script.py.mako`.
- Create `backend/migrations/versions/20260821_0001_phase1_domain_evidence.py`.
- Create `backend/src/deepaha/db/__init__.py`.
- Create `backend/src/deepaha/db/base.py`.
- Create `backend/src/deepaha/db/session.py`.
- Create `backend/src/deepaha/db/models.py` — import registry for all mapped classes.
- Create `backend/src/deepaha/sources/__init__.py` and `models.py`.
- Create `backend/src/deepaha/artifacts/__init__.py` and `models.py`.
- Create `backend/src/deepaha/documents/__init__.py` and `models.py`.
- Create `backend/src/deepaha/opportunities/__init__.py` and `models.py`.
- Create `backend/tests/integration/conftest.py`.
- Create `backend/tests/integration/test_migrations.py`.
- Create `backend/tests/integration/test_persistence_contract.py`.
- Create `infra/compose.yaml`.

### 对象存储与原始导入

- Create `backend/src/deepaha/artifacts/object_store.py` — Protocol, metadata and integrity error.
- Create `backend/src/deepaha/artifacts/s3.py` — boto3 implementation.
- Create `backend/src/deepaha/artifacts/service.py` — content addressing and idempotent import.
- Create `backend/tests/integration/test_s3_object_store.py`.
- Create `backend/tests/integration/test_raw_artifact_import.py`.

### 固定样本与 Gate

- Create `backend/tests/fixtures/official/civil-service-fast-stream-news-2025.json`.
- Create `backend/tests/fixtures/official/civil-service-fast-stream-news-2025.manifest.json`.
- Create `backend/tests/fixtures/official/README.md`.
- Create `backend/tests/integration/test_phase1_official_sample.py`.
- Create `scripts/verify-phase1.ps1`.
- Modify `.github/workflows/ci.yml`.
- Read/execute `scripts/verify.ps1` without modifying it; the pytest marker policy in `backend/pyproject.toml` keeps its existing `uv run pytest` command non-integration.
- Modify `docs/development/README.md` and `README.md` only after implementation status changes.
- Create `docs/gates/phase-1/README.md`.
- Create `docs/gates/phase-1/acceptance-results.md`.
- Create `docs/gates/phase-1/test-summary.md`.
- Create `docs/gates/phase-1/sample-provenance.md`.
- Create `docs/gates/phase-1/deferred-decisions.md`.

---

### Task 1：定义并导出五个 v0.1 契约

**文件：**

- Add: `docs/superpowers/specs/2026-08-21-phase-1-domain-contract-and-raw-evidence-design.md`
- Add: `docs/superpowers/plans/2026-08-21-phase-1-domain-contract-and-raw-evidence.md`
- Create: `backend/src/deepaha/contracts/__init__.py`
- Create: `backend/src/deepaha/contracts/common.py`
- Create: `backend/src/deepaha/contracts/phase1.py`
- Create: `backend/src/deepaha/contracts/export.py`
- Create: `backend/tests/contracts/test_phase1_contracts.py`
- Create: `contracts/schemas/v0.1.0/source.schema.json`
- Create: `contracts/schemas/v0.1.0/raw-artifact.schema.json`
- Create: `contracts/schemas/v0.1.0/document.schema.json`
- Create: `contracts/schemas/v0.1.0/opportunity.schema.json`
- Create: `contracts/schemas/v0.1.0/evidence-ref.schema.json`
- Create: `contracts/examples/v0.1.0/phase-1-official-sample.json`
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Modify: `docs/development/domain-contracts-v0.1.md`

**接口：**

- 产出：`SourceSchema`、`RawArtifactSchema`、`DocumentSchema`、`OpportunitySchema`、`EvidenceRefSchema`。
- 产出：`render_phase1_schemas() -> dict[str, bytes]` 和 `python -m deepaha.contracts.export <repo-root>`。
- 输入：spec 中已确认的 D1-D5。

- [x] **Step 1：先增加失败的契约测试**

Create tests that independently state the contract, including these cases:

```python
from datetime import UTC, datetime
from uuid import uuid4, uuid7

import pytest
from pydantic import ValidationError

from deepaha.contracts.phase1 import (
    EvidenceLocator,
    OpportunitySchema,
    OpportunityStatus,
    PublicationStatus,
)


def test_opportunity_accepts_unversioned_internal_identity() -> None:
    opportunity = OpportunitySchema(
        opportunity_id=uuid7(),
        public_id=f"opp_{uuid7().hex}",
        type="CIVIL_SERVICE",
        canonical_title="Civil Service Fast Stream",
        issuer_name="Civil Service Fast Stream",
        jurisdiction="United Kingdom",
        current_version=None,
        status=OpportunityStatus.UNKNOWN,
        publication_status=PublicationStatus.INTERNAL,
        created_at=datetime(2026, 8, 21, tzinfo=UTC),
        updated_at=datetime(2026, 8, 21, tzinfo=UTC),
    )

    assert opportunity.current_version is None


def test_entity_id_rejects_uuid4() -> None:
    with pytest.raises(ValidationError):
        OpportunitySchema(
            opportunity_id=uuid4(),
            public_id=f"opp_{uuid7().hex}",
            type="CIVIL_SERVICE",
            canonical_title="Contract fixture",
            issuer_name="Contract fixture issuer",
            jurisdiction=None,
            current_version=None,
            status="UNKNOWN",
            publication_status="INTERNAL",
            created_at=datetime(2026, 8, 21, tzinfo=UTC),
            updated_at=datetime(2026, 8, 21, tzinfo=UTC),
        )


def test_full_document_locator_has_fixed_value() -> None:
    assert EvidenceLocator(kind="full_document", value="*").value == "*"
    with pytest.raises(ValidationError):
        EvidenceLocator(kind="full_document", value="whole page")
```

Also test: naive datetime rejection, uppercase/short SHA rejection, `current_version=0` rejection, invalid enum rejection, `updated_at < created_at` rejection, and `storage_uri` rejecting endpoint credentials.

- [x] **Step 2：运行新测试并确认 RED**

Run:

```powershell
Set-Location backend
uv run pytest tests/contracts/test_phase1_contracts.py -v
```

Expected: collection fails because `deepaha.contracts` does not exist. This is the intended missing-contract failure.

- [x] **Step 3：增加直接依赖并锁定版本**

Run:

```powershell
Set-Location backend
uv add "pydantic>=2.11,<3"
uv add --group dev "jsonschema>=4.25,<5" "types-jsonschema>=4.25,<5"
```

Confirm `pyproject.toml` contains direct Pydantic and dev jsonschema dependencies and `uv.lock` changes only through `uv`.

- [x] **Step 4：实现公共校验类型**

Use Python 3.14 `uuid.uuid7` and Pydantic validators. The public signatures must be:

```python
EntityId = Annotated[UUID, AfterValidator(require_uuid7)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SourcePublicId = Annotated[str, StringConstraints(pattern=r"^src_[0-9a-f]{32}$")]
OpportunityPublicId = Annotated[str, StringConstraints(pattern=r"^opp_[0-9a-f]{32}$")]
S3Uri = Annotated[str, StringConstraints(pattern=r"^s3://[a-z0-9][a-z0-9.-]*/[^\s]+$")]
Confidence = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))]
```

`require_uuid7` rejects other UUID versions. A shared model validator converts aware times to UTC and rejects naive datetimes; it does not silently assume a timezone.

- [x] **Step 5：实现五个 Pydantic 契约**

Define the exact fields and enums from spec section 6. Set `model_config = ConfigDict(extra="forbid")` on all public contracts. `EvidenceLocator` enforces `full_document -> "*"`. `OpportunitySchema` permits `current_version=None` or an integer `>=1`.

Export all public names from `contracts/__init__.py`; do not add API routes or ORM imports.

- [x] **Step 6：实现确定性 JSON Schema 导出**

The renderer must return bytes without writing during tests:

```python
PHASE1_SCHEMAS: dict[str, type[BaseModel]] = {
    "source.schema.json": SourceSchema,
    "raw-artifact.schema.json": RawArtifactSchema,
    "document.schema.json": DocumentSchema,
    "opportunity.schema.json": OpportunitySchema,
    "evidence-ref.schema.json": EvidenceRefSchema,
}


def render_phase1_schemas() -> dict[str, bytes]:
    return {
        name: (
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        for name, model in PHASE1_SCHEMAS.items()
    }
```

The CLI writes only to `contracts/schemas/v0.1.0/` beneath the explicit repository root argument.

- [x] **Step 7：增加版本化示例与导出物**

Create one valid example object per contract in `phase-1-official-sample.json`. Use fixed UUIDv7 values, UTC timestamps, `status=UNKNOWN`, `publication_status=INTERNAL`, `current_version=null`, and the fixed SHA `1589f9177e197a578c8d37bd5a3bc869a17d7b0936f156666f69a2f88fbb9d2b`.

Run:

```powershell
Set-Location backend
$env:PYTHONPATH = "src"
uv run python -m deepaha.contracts.export ..
Remove-Item Env:PYTHONPATH
```

Add tests that validate every example with both its Pydantic model and `jsonschema.Draft202012Validator`, and compare `render_phase1_schemas()` byte-for-byte with the checked-in files.

- [x] **Step 8：用已确认的差异更新领域契约文档**

Change only these semantics:

- `Opportunity.current_version` becomes `VersionNumber | null` with the Phase 1 unversioned meaning.
- RawArtifact repeated fixed-capture replay uses `(source_id, content_sha256)` and rejects conflicting provenance.
- persistence splits `storage_uri` into bucket/key without changing the public field.
- EvidenceRef remains a public value object and gets an internal database ID only.
- `full_document` uses locator value `*` in Phase 1.

Keep all Phase 2+ objects `PROPOSED`; do not claim the Phase 1 contract is stable before the Gate closes.

- [x] **Step 9：运行契约 RED-to-GREEN 验证**

Run:

```powershell
Set-Location backend
uv run pytest tests/contracts/test_phase1_contracts.py -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
```

Expected: all contract tests pass and all three static checks exit `0`.

- [x] **Step 10：提交 Task 1**

```powershell
git add backend/pyproject.toml backend/uv.lock backend/src/deepaha/contracts backend/tests/contracts contracts docs/development/domain-contracts-v0.1.md docs/superpowers/specs/2026-08-21-phase-1-domain-contract-and-raw-evidence-design.md docs/superpowers/plans/2026-08-21-phase-1-domain-contract-and-raw-evidence.md
git commit -m "feat(contracts): define phase 1 domain schemas"
```

---

### Task 2：增加 PostgreSQL 18 持久化与迁移约束

**文件：**

- Modify: `backend/src/deepaha/core/settings.py`
- Modify: `backend/tests/core/test_settings.py`
- Create: `backend/src/deepaha/db/__init__.py`
- Create: `backend/src/deepaha/db/base.py`
- Create: `backend/src/deepaha/db/session.py`
- Create: `backend/src/deepaha/db/models.py`
- Create: `backend/src/deepaha/sources/__init__.py`
- Create: `backend/src/deepaha/sources/models.py`
- Create: `backend/src/deepaha/artifacts/__init__.py`
- Create: `backend/src/deepaha/artifacts/models.py`
- Create: `backend/src/deepaha/documents/__init__.py`
- Create: `backend/src/deepaha/documents/models.py`
- Create: `backend/src/deepaha/opportunities/__init__.py`
- Create: `backend/src/deepaha/opportunities/models.py`
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/script.py.mako`
- Create: `backend/migrations/versions/20260821_0001_phase1_domain_evidence.py`
- Create: `backend/tests/integration/conftest.py`
- Create: `backend/tests/integration/test_migrations.py`
- Create: `backend/tests/integration/test_persistence_contract.py`
- Create: `infra/compose.yaml`
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`

**接口：**

- 产出：`Base`、`get_engine()`、`session_factory()` 及五个 ORM 映射。
- 产出：Alembic revision `20260821_0001`。
- 输入：Task 1 Pydantic 契约和已确认的持久化映射。

- [x] **Step 1：先增加失败的设置测试**

Add tests for these environment variables:

```python
def test_settings_read_phase1_storage_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DEEPAHA_DATABASE_URL",
        "postgresql+psycopg://deepaha:local@127.0.0.1:55432/deepaha",
    )
    monkeypatch.setenv("DEEPAHA_OBJECT_STORE_ENDPOINT", "http://127.0.0.1:55000")
    monkeypatch.setenv("DEEPAHA_OBJECT_STORE_BUCKET", "deepaha-raw")
    monkeypatch.setenv("DEEPAHA_OBJECT_STORE_ACCESS_KEY", "local-access")
    monkeypatch.setenv("DEEPAHA_OBJECT_STORE_SECRET_KEY", "local-secret")

    settings = Settings()

    assert settings.database_url is not None
    assert settings.object_store_secret_key is not None
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert str(settings.object_store_endpoint) == "http://127.0.0.1:55000/"
    assert settings.object_store_secret_key.get_secret_value() == "local-secret"
    assert "local-secret" not in repr(settings)
```

- [x] **Step 2：运行设置测试并确认 RED**

Run `uv run pytest tests/core/test_settings.py -v` from `backend`.

Expected: failure because the Phase 1 settings fields do not exist.

- [x] **Step 3：增加数据库依赖与设置**

Run:

```powershell
Set-Location backend
uv add "sqlalchemy>=2.0,<3" "alembic>=1.16,<2" "psycopg[binary]>=3.2,<4"
```

Add optional Phase 1 settings so the existing health application can still start without infrastructure. Endpoint, region and bucket have development-safe defaults; `database_url`, access key and secret key default to `None`, and infrastructure constructors reject missing values when invoked. Credentials use `SecretStr`. Integration scripts set explicit local values.

- [x] **Step 4：创建本地服务定义**

`infra/compose.yaml` must use these images and host bindings:

```yaml
services:
  postgres:
    image: postgres:18.4-alpine3.23
    environment:
      POSTGRES_DB: deepaha
      POSTGRES_USER: deepaha
      POSTGRES_PASSWORD: deepaha_local_only
    ports:
      - "127.0.0.1:55432:5432"
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
      - "127.0.0.1:55000:5000"
```

PostgreSQL 18+ 的官方镜像把 `PGDATA` 放在 `/var/lib/postgresql/18/docker`，并把 `VOLUME` 移到 `/var/lib/postgresql`；上面的 `tmpfs` 明确覆盖该边界，避免 Compose 产生跨验证遗留的匿名数据库卷。Phase 1 不增加 bind mount 或 named volume。

- [x] **Step 5：编写失败的迁移与数据库契约测试**

Mark all database tests with `pytest.mark.integration`. Required assertions:

```python
def test_database_is_postgresql_18(connection: Connection) -> None:
    version_num = int(connection.exec_driver_sql("show server_version_num").scalar_one())
    assert 180000 <= version_num < 190000


def test_migration_matches_orm_metadata(connection: Connection) -> None:
    context = MigrationContext.configure(connection)
    assert compare_metadata(context, Base.metadata) == []


def test_document_and_opportunity_are_distinct_tables(inspector: Inspector) -> None:
    document_columns = {item["name"] for item in inspector.get_columns("documents")}
    opportunity_columns = {item["name"] for item in inspector.get_columns("opportunities")}
    assert "opportunity_id" not in document_columns
    assert "document_id" not in opportunity_columns
    assert "artifact_id" not in opportunity_columns
```

Also add real insert tests proving: UUIDv4 is rejected, duplicate Source URL is rejected, duplicate `(source_id, content_sha256)` is rejected, malformed hash is rejected, byte size `0` is rejected, `current_version=0` is rejected, and EvidenceRef document/artifact mismatch is rejected.

- [x] **Step 6：启动本地 PostgreSQL 并确认迁移 RED**

Run:

```powershell
docker compose -f infra/compose.yaml -p deepaha-phase1-plan up -d postgres
Set-Location backend
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_local_only@127.0.0.1:55432/deepaha"
uv run pytest tests/integration/test_migrations.py tests/integration/test_persistence_contract.py -m integration -v
```

Expected: failure because Alembic configuration, tables and mappings do not exist.

- [x] **Step 7：实现 Base、会话所有权与领域映射**

Use SQLAlchemy typed mappings. `db/base.py` defines a deterministic naming convention for indexes, unique constraints, checks, foreign keys and primary keys. `db/session.py` creates an engine from explicit Settings and never logs the URL.

Implement table columns and constraints exactly as spec section 7.2. Required database expressions include:

```sql
uuid_extract_version(source_id) = 7
content_sha256 ~ '^[0-9a-f]{64}$'
byte_size > 0
http_status is null or http_status between 100 and 599
current_version is null or current_version >= 1
```

The `RawArtifact.storage_uri` ORM property returns `f"s3://{storage_bucket}/{object_key}"`. `EvidenceRef` has internal UUIDv7 `evidence_ref_id`, but the contract adapter returns only public fields.

- [x] **Step 8：实现 Alembic 配置与初始 revision**

Set revision metadata exactly:

```python
revision = "20260821_0001"
down_revision = None
branch_labels = None
depends_on = None
```

`migrations/env.py` imports `deepaha.db.models` before reading `Base.metadata`, reads the URL from Settings, and supports online migration only for this phase. The revision creates tables in dependency order `sources`, `raw_artifacts`, `documents`, `opportunities`, `evidence_refs`; downgrade reverses that order.

- [x] **Step 9：增加隔离的迁移往返 fixture**

The migration test creates a uniquely named temporary database through the `postgres` maintenance database, runs `upgrade head -> downgrade base -> upgrade head`, and drops only that exact temporary database in `finally`. Validate the generated database name against `^deepaha_migration_[0-9a-f]{32}$` before executing `DROP DATABASE`.

- [x] **Step 10：运行数据库 GREEN 验证**

Run:

```powershell
Set-Location backend
uv run alembic upgrade head
uv run pytest tests/integration/test_migrations.py tests/integration/test_persistence_contract.py -m integration -v
uv run alembic check
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
```

Expected: PostgreSQL 18 assertion passes, migration round-trip passes, invalid inserts are rejected, metadata comparison is empty, and static checks exit `0`.

- [x] **Step 11：停止本 Task 范围内的本地服务**

From repository root run:

```powershell
docker compose -f infra/compose.yaml -p deepaha-phase1-plan down --remove-orphans
```

This removes only containers created with the exact `deepaha-phase1-plan` project name.

- [x] **Step 12：提交 Task 2**

```powershell
git add backend/pyproject.toml backend/uv.lock backend/alembic.ini backend/migrations backend/src/deepaha/core/settings.py backend/src/deepaha/db backend/src/deepaha/sources backend/src/deepaha/artifacts backend/src/deepaha/documents backend/src/deepaha/opportunities backend/tests/core/test_settings.py backend/tests/integration infra/compose.yaml
git commit -m "feat(db): add phase 1 PostgreSQL persistence"
```

---

### Task 3：实现 S3 兼容的不可变对象存储

**文件：**

- Create: `backend/src/deepaha/artifacts/object_store.py`
- Create: `backend/src/deepaha/artifacts/s3.py`
- Create: `backend/tests/integration/test_s3_object_store.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`

**接口：**

- 产出：`ObjectStore`、`ObjectMetadata`、`ObjectIntegrityError`、`S3ObjectStore`。
- 输入：Task 2 的对象存储设置。

- [x] **Step 1：编写失败的真实边界对象存储测试**

Test the adapter rather than a mock:

```python
def test_put_if_absent_reuses_identical_object(object_store: S3ObjectStore) -> None:
    content = b"phase-1-raw-evidence"
    digest = sha256(content).hexdigest()
    key = f"raw/sha256/{digest[:2]}/{digest}"

    first = object_store.put_bytes_if_absent(
        key=key,
        content=content,
        media_type="application/octet-stream",
        sha256=digest,
    )
    second = object_store.put_bytes_if_absent(
        key=key,
        content=content,
        media_type="application/octet-stream",
        sha256=digest,
    )

    assert second == first
    assert object_store.get_bytes(key=key) == content


def test_existing_object_with_wrong_metadata_is_never_overwritten(
    object_store: S3ObjectStore,
) -> None:
    with pytest.raises(ObjectIntegrityError):
        object_store.put_bytes_if_absent(
            key="raw/sha256/00/" + "0" * 64,
            content=b"not-zero-hash",
            media_type="application/octet-stream",
            sha256="0" * 64,
        )
```

- [x] **Step 2：启动 Moto 并确认 RED**

Run:

```powershell
docker compose -f infra/compose.yaml -p deepaha-phase1-storage up -d s3
Set-Location backend
$env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55000"
$env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
$env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "phase1-local"
$env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "phase1-local-secret"
uv run pytest tests/integration/test_s3_object_store.py -m integration -v
```

Expected: import failure because object-store modules do not exist.

- [x] **Step 3：增加 S3 依赖**

Run:

```powershell
Set-Location backend
uv add "boto3>=1.40,<2"
uv add --group dev "boto3-stubs[s3]>=1.40,<2"
```

- [x] **Step 4：实现对象存储 Protocol 与元数据**

Use these exact public shapes:

```python
@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    bucket: str
    key: str
    byte_size: int
    sha256: str
    media_type: str | None


class ObjectStore(Protocol):
    def ensure_bucket(self) -> None:
        raise NotImplementedError
    def put_bytes_if_absent(
        self, *, key: str, content: bytes, media_type: str | None, sha256: str
    ) -> ObjectMetadata:
        raise NotImplementedError
    def get_bytes(self, *, key: str) -> bytes:
        raise NotImplementedError
    def stat(self, *, key: str) -> ObjectMetadata:
        raise NotImplementedError
```

`ObjectIntegrityError` is raised for caller-supplied hash mismatch or existing-object metadata mismatch.

- [x] **Step 5：实现 `S3ObjectStore`**

Requirements:

- path-style addressing and Signature v4 for local endpoint compatibility;
- `ensure_bucket()` treats an existing owned bucket as success;
- calculate SHA-256 locally before any request;
- conditional create using `IfNoneMatch="*"`;
- on 409/412, call `stat()` and accept only exact size/hash equality;
- save `sha256` in S3 user metadata and content type when known;
- `get_bytes()` re-hashes the body and raises on mismatch;
- never log access/secret keys or response bodies.

- [x] **Step 6：运行对象存储 GREEN 验证**

Run:

```powershell
Set-Location backend
uv run pytest tests/integration/test_s3_object_store.py -m integration -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
```

Expected: all object-store tests pass against Moto and all three static checks exit `0`.

- [x] **Step 7：停止本 Task 范围内的 Moto 服务**

Run `docker compose -f infra/compose.yaml -p deepaha-phase1-storage down --remove-orphans` from the repository root.

- [x] **Step 8：提交 Task 3**

```powershell
git add backend/pyproject.toml backend/uv.lock backend/src/deepaha/artifacts/object_store.py backend/src/deepaha/artifacts/s3.py backend/tests/integration/test_s3_object_store.py
git commit -m "feat(storage): add immutable S3 raw object store"
```

---

### Task 4：实现 RawArtifact 幂等导入

**文件：**

- Create: `backend/src/deepaha/artifacts/service.py`
- Create: `backend/tests/integration/test_raw_artifact_import.py`
- Modify: `backend/src/deepaha/artifacts/__init__.py`

**接口：**

- 产出：`ImportRawArtifactCommand`、`ImportRawArtifactResult`、`RawArtifactProvenanceConflict`、`build_raw_object_key()`、`import_raw_artifact()`。
- 输入：Task 2 的 Session/ORM 与 Task 3 的 `ObjectStore`。

- [x] **Step 1：编写失败的幂等性测试**

```python
def test_replaying_same_capture_returns_same_raw_artifact(
    session: Session,
    object_store: S3ObjectStore,
    source: Source,
) -> None:
    command = ImportRawArtifactCommand(
        source_id=source.source_id,
        requested_url="https://example.gov/official.json",
        resolved_url="https://example.gov/official.json",
        retrieved_at=datetime(2026, 8, 21, 9, 59, 8, 5000, tzinfo=UTC),
        http_status=200,
        media_type="application/json; charset=utf-8",
        content=b'{"official":true}',
        collector_version="phase1_fixture/0.1.0",
        metadata_schema_version="0.1.0",
    )

    first = import_raw_artifact(session=session, object_store=object_store, command=command)
    second = import_raw_artifact(session=session, object_store=object_store, command=command)

    assert first.created is True
    assert second.created is False
    assert second.artifact.artifact_id == first.artifact.artifact_id
    assert session.scalar(select(func.count()).select_from(RawArtifact)) == 1
```

Add separate tests for changed `retrieved_at` causing `RawArtifactProvenanceConflict`, a transaction rollback followed by successful retry, object key format, and zero-byte rejection before storage.

- [x] **Step 2：运行定向测试并确认 RED**

Run from the repository root:

```powershell
docker compose -f infra/compose.yaml -p deepaha-phase1-import up -d --wait postgres s3
Set-Location backend
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_local_only@127.0.0.1:55432/deepaha"
$env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55000"
$env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
$env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
$env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "phase1-local"
$env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "phase1-local-secret"
uv run alembic upgrade head
uv run pytest tests/integration/test_raw_artifact_import.py -m integration -v
```

Expected: import failure because `artifacts.service` does not exist.

- [x] **Step 3：实现命令/结果类型与内容寻址**

Use frozen dataclasses. `build_raw_object_key` must return:

```python
def build_raw_object_key(content_sha256: str) -> str:
    return f"raw/sha256/{content_sha256[:2]}/{content_sha256}"
```

Validate non-empty bytes and all command metadata with the Task 1 contract types before calling storage.

- [x] **Step 4：实现数据库幂等性，服务内部不提交事务**

The service order is:

1. hash bytes and derive key;
2. `put_bytes_if_absent` and verify metadata;
3. SQLAlchemy PostgreSQL `insert(RawArtifact).values(candidate).on_conflict_do_nothing(index_elements=[RawArtifact.source_id, RawArtifact.content_sha256]).returning(RawArtifact.artifact_id)`;
4. if inserted, load and return `created=True`;
5. if conflicted, load the existing row and compare requested/resolved URL, retrieved time, status, media type, byte size, collector version, metadata schema version, bucket and object key;
6. exact match returns `created=False`; any mismatch raises `RawArtifactProvenanceConflict(code="RAW_ARTIFACT_PROVENANCE_CONFLICT")`.

The caller owns commit/rollback. The service never deletes the content-addressed object on database rollback.

- [x] **Step 5：证明测试能捕获错误的去重分支**

Temporarily change the conflict branch to always create a fresh ID, run the duplicate test, and confirm it fails on either the unique constraint or row count. Restore the correct implementation and rerun to pass.

- [x] **Step 6：运行 Task 4 GREEN 验证**

Run:

```powershell
Set-Location backend
uv run pytest tests/integration/test_raw_artifact_import.py -m integration -v
uv run pytest tests/integration -m integration -v
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
```

Expected: duplicate replay returns one ID/row, provenance conflict is explicit, rollback retry succeeds, and all commands exit `0`.

- [x] **Step 7：停止本 Task 服务并提交 Task 4**

```powershell
Set-Location ..
docker compose -f infra/compose.yaml -p deepaha-phase1-import down --remove-orphans
git add backend/src/deepaha/artifacts backend/tests/integration/test_raw_artifact_import.py
git commit -m "feat(artifacts): add idempotent raw evidence import"
```

---

### Task 5：增加许可清晰的官方样本与纵向证据证明

**文件：**

- Create: `backend/tests/fixtures/official/civil-service-fast-stream-news-2025.json`
- Create: `backend/tests/fixtures/official/civil-service-fast-stream-news-2025.manifest.json`
- Create: `backend/tests/fixtures/official/README.md`
- Create: `backend/tests/integration/test_phase1_official_sample.py`

**接口：**

- 产出：不可变 fixture 字节和来源 manifest。
- 输入：全部 Phase 1 契约、ORM 模型、对象存储和导入服务。

- [x] **Step 1：编写失败的 fixture 身份测试**

```python
FIXED_SHA256 = "1589f9177e197a578c8d37bd5a3bc869a17d7b0936f156666f69a2f88fbb9d2b"
FIXED_SIZE = 11662


def test_official_fixture_has_fixed_bytes_and_open_licence() -> None:
    content = FIXTURE_PATH.read_bytes()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert len(content) == FIXED_SIZE
    assert sha256(content).hexdigest() == FIXED_SHA256
    assert manifest["content_sha256"] == FIXED_SHA256
    assert manifest["byte_size"] == FIXED_SIZE
    assert manifest["license"]["name"] == "Open Government Licence v3.0"
    assert manifest["limitations"]["gold_business_sample"] is False
    assert manifest["limitations"]["current_application_status_proven"] is False
```

- [x] **Step 2：运行 fixture 测试并确认 RED**

Run:

```powershell
Set-Location backend
uv run pytest tests/integration/test_phase1_official_sample.py::test_official_fixture_has_fixed_bytes_and_open_licence -v
```

Expected: failure because fixture and manifest do not exist.

- [x] **Step 3：只捕获已经固定的官方响应**

Retrieve exactly:

```text
https://www.gov.uk/api/content/government/news/civil-service-fast-stream-named-uks-top-graduate-employer
```

Before adding it, calculate bytes and require all fixed values:

```text
retrieved_at = 2026-08-21T09:59:08.005Z
http_status = 200
media_type = application/json; charset=utf-8
byte_size = 11662
sha256 = 1589f9177e197a578c8d37bd5a3bc869a17d7b0936f156666f69a2f88fbb9d2b
```

If a fresh GET no longer produces the fixed bytes, stop this Task and report that the selected snapshot cannot be reconstructed from the current source. Do not accept a new hash without user approval. Add the fixed UTF-8 response with `apply_patch`; do not add response headers, images, cookies or unrelated assets.

- [x] **Step 4：增加精确的来源 manifest 与 README**

The manifest must contain these literal domain values:

```json
{
  "requested_url": "https://www.gov.uk/api/content/government/news/civil-service-fast-stream-named-uks-top-graduate-employer",
  "resolved_url": "https://www.gov.uk/api/content/government/news/civil-service-fast-stream-named-uks-top-graduate-employer",
  "retrieved_at": "2026-08-21T09:59:08.005Z",
  "http_status": 200,
  "media_type": "application/json; charset=utf-8",
  "byte_size": 11662,
  "content_sha256": "1589f9177e197a578c8d37bd5a3bc869a17d7b0936f156666f69a2f88fbb9d2b",
  "collector_version": "phase1_design_capture/0.1.0",
  "metadata_schema_version": "0.1.0",
  "license": {
    "name": "Open Government Licence v3.0",
    "url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    "terms_url": "https://www.gov.uk/help/terms-conditions",
    "attribution": "Contains public sector information licensed under the Open Government Licence v3.0."
  },
  "limitations": {
    "gold_business_sample": false,
    "china_launch_coverage": false,
    "current_application_status_proven": false
  }
}
```

README records the two official organizations, source page link, licence/attribution, no third-party assets, and the non-Gold/non-current-status limitations.

- [x] **Step 5：编写失败的纵向集成测试**

The test must:

1. create Source with `tier=OFFICIAL_PRIMARY` and authority `Government Skills and Civil Service Fast Stream`;
2. call `import_raw_artifact` twice with the exact fixture/manifest;
3. create Document title `Civil Service Fast Stream named UK's top graduate employer`, published at `2025-09-16T23:00:00Z` (the UTC value stated by the fixed response), language `en`, parser `phase1_fixture_manifest/0.1.0`;
4. create EvidenceRef `full_document`, `*`, quote hash equal to the raw hash;
5. create Opportunity title `Civil Service Fast Stream`, type `CIVIL_SERVICE`, status `UNKNOWN`, publication `INTERNAL`, current version `null`;
6. commit, reload all rows, read bytes from S3, and assert exact equality/hash;
7. assert one RawArtifact row, same ID from both imports, distinct Document/Opportunity IDs and titles, and no direct document/artifact columns in Opportunity.

Run it before adding any missing fixture-to-ORM adapters and confirm the specific failure.

- [x] **Step 6：只增加测试需要的最小 fixture 映射**

Keep mapping code in the test fixture helpers unless it is used by production import. Do not create a generic JSON parser, Source Registry, resolver or sample-specific runtime API. Use the existing ORM constructors and raw import service.

- [x] **Step 7：运行官方样本 GREEN 验证**

Run from the repository root:

```powershell
docker compose -f infra/compose.yaml -p deepaha-phase1-sample up -d --wait postgres s3
Set-Location backend
$env:DEEPAHA_DATABASE_URL = "postgresql+psycopg://deepaha:deepaha_local_only@127.0.0.1:55432/deepaha"
$env:DEEPAHA_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:55000"
$env:DEEPAHA_OBJECT_STORE_REGION = "us-east-1"
$env:DEEPAHA_OBJECT_STORE_BUCKET = "deepaha-raw"
$env:DEEPAHA_OBJECT_STORE_ACCESS_KEY = "phase1-local"
$env:DEEPAHA_OBJECT_STORE_SECRET_KEY = "phase1-local-secret"
uv run alembic upgrade head
uv run pytest tests/integration/test_phase1_official_sample.py -m integration -v
uv run pytest tests/contracts tests/integration -v
```

Expected: fixed identity and licence tests pass; the vertical test proves raw byte replay and Document/Opportunity separation without network access.

- [x] **Step 8：停止本 Task 范围内的服务**

Run from the repository root:

```powershell
docker compose -f infra/compose.yaml -p deepaha-phase1-sample down --remove-orphans
```

- [x] **Step 9：提交 Task 5**

```powershell
git add backend/tests/fixtures/official backend/tests/integration/test_phase1_official_sample.py
git commit -m "test(phase1): add licensed official evidence slice"
```

---

### Task 6：增加可复现的本地与 CI Phase 1 验证

**文件：**

- Create: `scripts/verify-phase1.ps1`
- Modify: `.github/workflows/ci.yml`
- Modify: `backend/pyproject.toml`
- Read/execute only: `scripts/verify.ps1`

**接口：**

- 产出：一个 Phase 1 集成验证命令和 CI `integration` 作业。
- 输入：Task 1-5 的全部测试/迁移。

- [x] **Step 1：让基线 pytest 明确排除集成测试**

Task 2 已注册 marker；本 Step 只把默认测试切换为显式排除集成测试，使 `uv run pytest` 在无 Docker 时保持确定性：

```toml
[tool.pytest.ini_options]
addopts = "-q -m 'not integration'"
markers = ["integration: requires PostgreSQL 18 and the local S3 endpoint"]
pythonpath = ["src"]
testpaths = ["tests"]
```

Run `uv run pytest --strict-markers`; expected baseline unit/contract tests pass and integration tests are deselected, not silently skipped.

- [x] **Step 2：编写带范围化清理的 `verify-phase1.ps1`**

The script must:

- set `$ErrorActionPreference = "Stop"`;
- resolve the repository root from `$PSScriptRoot`;
- use `$phase1ComposeProject = "deepaha-phase1-$PID"`;
- set the local database/S3 environment variables shown in previous Tasks;
- run root `scripts/verify.ps1`;
- start `postgres` and `s3` with `docker compose -f (Join-Path $projectRoot "infra/compose.yaml") -p $phase1ComposeProject up -d --wait postgres s3`;
- run `uv sync --locked --group dev`, `uv run alembic upgrade head`, `uv run pytest -m integration --strict-markers`, and `uv run alembic check` from `backend`;
- in `finally`, run `docker compose -f (Join-Path $projectRoot "infra/compose.yaml") -p $phase1ComposeProject down --remove-orphans`;
- never call `down -v`, delete filesystem paths, or touch another Compose project.

- [x] **Step 3：用故意失败的断言运行一次脚本**

Temporarily change the fixed expected SHA in the official sample test by one character. Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-phase1.ps1
```

Expected: non-zero exit and the SHA assertion failure. Restore the fixed SHA before continuing.

- [x] **Step 4：恢复后运行完整本地验证**

Run the same script again. Expected: baseline backend/web verification, migrations, integration tests and Alembic check all exit `0`; scoped containers stop in `finally`.

- [x] **Step 5：增加 CI `integration` 作业**

Use service containers:

```yaml
  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:18.4-alpine3.23
        env:
          POSTGRES_DB: deepaha
          POSTGRES_USER: deepaha
          POSTGRES_PASSWORD: deepaha_local_only
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U deepaha -d deepaha"
          --health-interval 2s --health-timeout 2s --health-retries 30
      s3:
        image: motoserver/moto:5.2.2
        ports: ["5000:5000"]
    env:
      DEEPAHA_DATABASE_URL: postgresql+psycopg://deepaha:deepaha_local_only@127.0.0.1:5432/deepaha
      DEEPAHA_OBJECT_STORE_ENDPOINT: http://127.0.0.1:5000
      DEEPAHA_OBJECT_STORE_REGION: us-east-1
      DEEPAHA_OBJECT_STORE_BUCKET: deepaha-raw
      DEEPAHA_OBJECT_STORE_ACCESS_KEY: phase1-ci
      DEEPAHA_OBJECT_STORE_SECRET_KEY: phase1-ci-secret
```

Steps use checkout, `astral-sh/setup-uv@v6` with Python 3.14, locked sync, `alembic upgrade head`, `pytest -m integration --strict-markers`, and `alembic check`. The credentials are local service constants, not external secrets; label them as test-only in workflow comments.

- [x] **Step 6：运行本地 YAML 与仓库检查**

Run:

```powershell
git diff --check
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify-phase1.ps1
```

Read complete output and record actual test counts, migration revision and tool versions for Task 7.

- [x] **Step 7：提交 Task 6**

```powershell
git add backend/pyproject.toml backend/uv.lock scripts/verify.ps1 scripts/verify-phase1.ps1 .github/workflows/ci.yml
git commit -m "ci: add phase 1 integration verification"
```

---

### Task 7：生成如实的 Phase 1 Gate 证据，仅凭真实证明关闭 Gate

**文件：**

- Create: `docs/gates/phase-1/README.md`
- Create: `docs/gates/phase-1/acceptance-results.md`
- Create: `docs/gates/phase-1/test-summary.md`
- Create: `docs/gates/phase-1/sample-provenance.md`
- Create: `docs/gates/phase-1/deferred-decisions.md`
- Modify: `docs/development/README.md`
- Modify: `docs/development/domain-contracts-v0.1.md`
- Modify: `README.md`

**接口：** 仅 Gate 证据；不增加运行时行为。

- [x] **Step 1：实现后先以 `OPEN` 状态创建证据包**

Populate files from actual Task 6 outputs. Before remote CI succeeds, `README.md` must say:

```markdown
> Gate 状态：`OPEN`
> 实现状态：`IMPLEMENTED`
> 远程 CI：等待当前实现提交的实际运行证据
```

Do not copy Phase 0 test counts or CI URLs. `sample-provenance.md` must reproduce the fixed URL, time, licence, 11662-byte size, SHA and object key exactly.

- [x] **Step 2：运行新鲜副本验证**

Create a temporary clone or archive extraction outside `D:\DeepAha`, install only documented prerequisites, and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify-phase1.ps1
```

Record the temporary path, source commit, runtime/container versions, commands, exit codes, test counts and migration revision. The temporary copy must not reuse repository `.venv`, caches, database files or object-store contents.

- [x] **Step 3：逐行验证验收矩阵**

`acceptance-results.md` must contain one row for each exit condition:

1. duplicate import leaves one RawArtifact;
2. raw bytes/URL/time/hash/bucket/key reproduce input;
3. Document and Opportunity are separate;
4. Schema/migration/ORM/tests agree;
5. fresh environment reproduces all results;
6. no Phase 2 capability or prohibited artifact was added.

Each PASS row cites a concrete test name, command and observed result. Any missing evidence keeps that row and the Gate open.

- [x] **Step 4：检查最终 Diff 的范围与秘密信息**

Run:

```powershell
git status --short
git diff --check
git diff --stat 22f11b8e99311067670d8bbf1394fb881bf7e872..HEAD
git ls-files | rg "(^|/)(\.env|.*\.db|.*\.sqlite|node_modules|\.next|\.venv|__pycache__|objects?|data)(/|$)"
rg -n --hidden -g '!backend/uv.lock' -g '!web/pnpm-lock.yaml' "AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|postgresql[^\s]+:[^\s]+@" .
```

Review matches manually. Test-only local credentials in Compose/CI are permitted only when clearly labelled and unable to access external services.

- [x] **Step 5：提交 OPEN Gate 证据**

```powershell
git add docs/gates/phase-1 docs/development/README.md README.md
git commit -m "docs: record phase 1 local verification evidence"
```

- [x] **Step 6：仅在用户授权 push 后取得远程 CI 证据**

If the user authorizes pushing, push the implementation branch/commit, wait for `backend-quality`, `web-quality`, and `integration`, and inspect all conclusions. If push is not authorized, stop with Gate `OPEN` and report the missing remote evidence; do not fabricate a run URL.

- [x] **Step 7：只在远程成功后关闭 Gate**

When all required jobs are `success`, update:

- Gate status to `CLOSED`;
- current verification commit and Actions run URL;
- actual job conclusions;
- development/root status text to “Phase 1 implemented and verified”; and
- the five approved Phase 1 objects to `STABLE` in the domain contract while leaving Phase 2+ objects `PROPOSED`.

Run `git diff --check` and both verification scripts again after the documentation-only change if the source commit changed.

- [x] **Step 8：提交最终 Gate 关闭记录**

```powershell
git add docs/gates/phase-1 docs/development docs/development/domain-contracts-v0.1.md README.md
git commit -m "docs: close phase 1 domain evidence gate"
```

Do not push this closure commit or claim the new commit's CI passed until its own required workflow run succeeds.

---

## 最终验证清单

Before reporting Phase 1 complete, execute and read fresh output for every item:

- [x] `git status --short --branch` shows only expected state.
- [x] `git diff --check` exits `0`.
- [x] `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` exits `0`.
- [x] `powershell -ExecutionPolicy Bypass -File scripts/verify-phase1.ps1` exits `0` in the working copy.
- [x] The same two commands exit `0` in a fresh copy.
- [x] Alembic round-trip and `alembic check` pass against PostgreSQL 18.4.
- [x] The fixed fixture is exactly 11662 bytes with SHA `1589f9177e197a578c8d37bd5a3bc869a17d7b0936f156666f69a2f88fbb9d2b`.
- [x] Repeated import returns one RawArtifact ID and one database row.
- [x] S3 readback bytes match the fixture exactly.
- [x] EvidenceRef rejects a Document/Artifact mismatch.
- [x] Document and Opportunity remain separate models/tables/entities.
- [x] Checked-in JSON Schemas equal deterministic Pydantic exports.
- [x] Alembic migration and SQLAlchemy metadata have no diff.
- [x] No secrets, user data, database/object files, caches or build output are tracked.
- [x] `backend-quality`, `web-quality`, and `integration` have actual remote `success` conclusions for the Gate commit.
- [x] Gate documents contain actual evidence and no planned result is described as completed.

## 交接

用户确认 D1-D7 和实施工作区后，使用 `superpowers:executing-plans` 原样执行本计划，在每个 Task 后停留复核；即使 Phase 1 关闭也不得进入 Phase 2。全部实现与验证完成后，使用 `superpowers:finishing-a-development-branch` 展示集成选项，由用户决定是否合并、创建 PR 或保留分支。
