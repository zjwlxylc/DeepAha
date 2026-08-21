# DeepAha Phase 4 Rules, Eligibility and Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Phase 3 精确候选提交之上，以受控堆叠方式实现可版本化、可审计、可确定性回放的规则、资格四态、匹配快照与合成评估候选，并保持 Phase 2/3 Gate 阻塞边界。

**Architecture:** 沿用现有 Python 模块化单体、Pydantic 权威契约、SQLAlchemy 2/Alembic/PostgreSQL 18 与薄持久化服务模式。纯领域模块负责受限规则编译、专业匹配、资格聚合与合成评估，数据库只保存显式版本、输入摘要、逐规则结论和证据引用；所有 v0.4 工件均为 `PROPOSED` 候选，不能覆盖 v0.1/v0.2/v0.3。

**Tech Stack:** Python 3.14、Pydantic 2、SQLAlchemy 2、Alembic、PostgreSQL 18、pytest、jsonschema、Ruff、mypy、PowerShell、Docker Compose、GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-08-22-phase-4-rules-eligibility-and-evaluation-design.md`

## Global Constraints

- 精确父基线必须是 `5a5847be266980e83eccd8718c23b77e788ee481`，Phase 4 分支为 `codex/phase-4-rules-eligibility-evaluation`，堆叠 PR base 为 `codex/phase-3-opportunity-resolution`。
- Phase 2 Gate 保持 `OPEN`，Phase 3 Gate 保持 `BLOCKED_BY_PHASE2`，v0.2/v0.3/v0.4 保持 `PROPOSED`；Phase 4 最终状态只能为 `IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES`。
- 不得访问或改动 Phase 2/3 工作区、分支或 compose project；不得访问 `deepaha-phase2-live-gate`，不得占用 55432/55000、55433/55001。
- Phase 4 集成验证只使用 compose project `deepaha-phase4-*`、PostgreSQL `55434` 与 Moto `55002`。
- 不创建子 Agent 或并行 Agent；本计划已按用户授权选择 `superpowers:executing-plans` 在当前会话连续执行，不等待常规 review checkpoint。
- 不修改 v0.1/v0.2/v0.3 Schema 字节、路径或已有导入；v0.4 只新增 `contracts/schemas/v0.4.0`、示例和 Python 类型。
- 固定资格状态只有 `ELIGIBLE`、`LIKELY_ELIGIBLE`、`UNCERTAIN`、`INELIGIBLE`；排序不得改变资格状态。
- `INELIGIBLE` 必须至少包含一条确定性冲突规则、官方证据引用且证据优先级不低于 300；缺失、模糊、冲突或仅语义候选最高为 `UNCERTAIN`。
- 证据优先级固定为：最新官方更正 600 > 正式岗位/政策附件 500 > 原始正式公告 400 > 官方 FAQ/指南 300 > 人工批准映射 200 > LLM 语义推断 100；Phase 4 不调用 LLM。
- 固定数据集必须零意外 `INELIGIBLE`；`<=0.5%` 仅是未来真实标注评估计划阈值，不能用合成样本宣称生产准确率。
- 默认测试不得访问实时站点、浏览器或模型；不实现 Phase 5/6、Redis/Valkey/Celery、pgvector、OCR、通知、反馈、商业化、真实用户/API/UI。
- 每个任务执行 RED → 最小实现 → 定向验证 → 风险相称回归 → `superpowers:verification-before-completion` → 独立提交 → 推送当前 Phase 4 分支。
- 任一 Phase 2/3 closing commit 改变基础契约时，停止晋升，更新到精确 closing commit，重做兼容审查并运行根验证与 Phase 4 全量验证。

## File Structure

### Existing files to modify

- `.gitattributes`：固定 Phase 3/4 逐字节 JSON fixture 使用 LF，消除 Windows `core.autocrlf=true` 对工作树摘要的影响。
- `backend/src/deepaha/contracts/__init__.py`：公开 v0.4 契约导入，不改旧名称。
- `backend/src/deepaha/contracts/export.py`：新增 `PHASE4_SCHEMAS`、v0.4 渲染/写出与 CLI 版本选项。
- `backend/src/deepaha/db/models.py`：仅导入 Phase 4 ORM 元数据模块，保证 Alembic/测试发现表。
- `backend/tests/integration/conftest.py`：允许 Phase 4 独立数据库和对象存储端点由既有环境变量注入，不写死 Phase 2/3 端口。
- `.github/workflows/ci.yml`：为 Phase 4 分支增加独立 scoped job，并保持旧 job 行为不变。
- `docs/development/README.md`、`docs/development/system-roadmap.md`、`docs/development/architecture.md`、`docs/development/quality-and-release.md`：增加 Phase 4 候选导航、边界和验证命令，保持计划/实现/验证状态分离。

### New contract and domain files

- `backend/src/deepaha/contracts/phase4.py`：v0.4 Pydantic 枚举和 Schema 的单一权威来源。
- `backend/src/deepaha/rules/types.py`：编译后不可变规则节点、字段类型注册表和编译错误。
- `backend/src/deepaha/rules/compiler.py`：受限 DSL 的确定性拓扑编译与类型检查。
- `backend/src/deepaha/rules/major.py`：版本化专业目录/人工映射加载与确定性匹配。
- `backend/src/deepaha/rules/models.py`：RuleSet/Rule/RuleEvidence ORM。
- `backend/src/deepaha/profiles/models.py`：ProfileSnapshot ORM。
- `backend/src/deepaha/eligibility/engine.py`：逐规则求值、证据约束和四态聚合纯函数。
- `backend/src/deepaha/eligibility/models.py`：EligibilityResult ORM。
- `backend/src/deepaha/eligibility/service.py`：保存匹配快照、幂等重放和差异摘要的薄服务。
- `backend/src/deepaha/matching/models.py`：MatchSnapshot 与逐规则结果 ORM。
- `backend/src/deepaha/evaluation/models.py`：EvaluationRun 与逐案例结果 ORM。
- `backend/src/deepaha/evaluation/fixtures.py`：固定 fixture 读取、摘要与一致性校验。
- `backend/src/deepaha/evaluation/runner.py`：批量合成回放和安全指标计算。
- 各新包 `__init__.py`：只导出稳定的 Phase 4 候选接口。

### New migration, schemas, fixtures, tests and evidence

- `backend/migrations/versions/20260822_0004_phase4_rules_eligibility_evaluation.py`：只新增 Phase 4 表、约束和索引，不重写旧数据。
- `contracts/schemas/v0.4.0/*.schema.json`：由 `phase4.py` 确定性导出的 7 个 v0.4 Schema。
- `contracts/examples/v0.4.0/phase-4-example.json`：可被全部 v0.4 Schema 分段验证的合成示例。
- `backend/tests/fixtures/evaluation/phase4-major-catalog.json`：许可安全的合成专业目录版本。
- `backend/tests/fixtures/evaluation/phase4-major-mapping.json`：人工批准映射候选版本。
- `backend/tests/fixtures/evaluation/phase4-golden-cases.json`：覆盖边界、缺失、冲突和错误否定保护的固定案例。
- `backend/tests/fixtures/evaluation/phase4-mother-profiles.json`：20 个母画像。
- `backend/tests/fixtures/evaluation/phase4-synthetic-profiles.json`：从 20 个母画像确定性派生的 100 个版本化合成画像。
- `backend/tests/fixtures/evaluation/phase4-fixtures.manifest.json`：逐文件 SHA-256、数量、许可与合成用途声明。
- `backend/tests/fixtures/evaluation/generate_phase4_fixtures.py`：固定种子、无网络的确定性 fixture 生成器。
- `backend/tests/contracts/test_phase4_contracts.py`：旧 Schema 不变、v0.4 模型/Schema/示例验证。
- `backend/tests/rules/test_compiler.py`、`test_major.py`：DSL 与专业匹配单元测试。
- `backend/tests/eligibility/test_engine.py`：四态、证据、日期边界与错误否定保护。
- `backend/tests/evaluation/test_fixtures.py`、`test_runner.py`：20/100 数量、manifest、重放与指标语义。
- `backend/tests/integration/test_phase4_persistence_contract.py`：迁移、外键、版本和 JSON 回放。
- `backend/tests/integration/test_phase4_match_replay.py`：相同输入幂等、版本差异可解释。
- `infra/compose.phase4.yaml`：独立 PostgreSQL 55434/Moto 55002。
- `scripts/verify-phase4.ps1`：Phase 4 scoped verifier。
- `docs/development/domain-contracts-v0.4.md`：候选契约、状态与兼容边界。
- `docs/gates/phase-4/README.md`、`acceptance-results.md`、`test-summary.md`、`evaluation-summary.md`、`security-and-compliance.md`、`deferred-decisions.md`、`operations.md`：候选证据包，始终声明双 Gate 阻塞。

---

### Task 0: Stabilize fixed-fixture bytes on Windows

**Files:**
- Modify: `.gitattributes`
- Verify only: `backend/tests/fixtures/opportunities/phase3-resolution-cases.json`

**Interfaces:**
- Consumes: Phase 3 fixture Git blob SHA-256 `1ab32974067886ca4f8977cd599c1fa5583ca95449371830907fc49cb28b7d34`。
- Produces: 在 `core.autocrlf=true` 下工作树仍为 LF、逐字节摘要与 Git blob 相同的固定 fixture 规则。

- [ ] **Step 1: Preserve the baseline RED evidence**

Run:

```powershell
Push-Location backend
uv run pytest tests/opportunities/test_resolver.py::test_resolution_fixture_bytes_are_fixed -q
Pop-Location
```

Expected: FAIL，工作树摘要为 `16c981ca...`，期望摘要为 `1ab32974...`；这是换行检出问题，不是 Phase 3 fixture 语义变化。

- [ ] **Step 2: Add exact LF attributes**

Append exactly:

```gitattributes
backend/tests/fixtures/opportunities/*.json text eol=lf
backend/tests/fixtures/evaluation/*.json text eol=lf
```

Do not change any Phase 3 JSON value.

- [ ] **Step 3: Re-materialize the one tracked fixture from the index using LF**

Run:

```powershell
git -c core.autocrlf=false checkout-index -f -- backend/tests/fixtures/opportunities/phase3-resolution-cases.json
git diff -- backend/tests/fixtures/opportunities/phase3-resolution-cases.json
git ls-files --eol backend/tests/fixtures/opportunities/phase3-resolution-cases.json
```

Expected: no JSON diff; `i/lf w/lf attr/text eol=lf`。

- [ ] **Step 4: Verify the fixed byte contract and root baseline**

Run:

```powershell
Push-Location backend
uv run pytest tests/opportunities/test_resolver.py::test_resolution_fixture_bytes_are_fixed -q
Pop-Location
& ./scripts/verify.ps1
```

Expected: targeted test PASS；根 verifier 的 Ruff、mypy、非集成 pytest 全部 PASS。

- [ ] **Step 5: Verify scope, commit and push**

Run:

```powershell
git diff --check
git diff -- .gitattributes backend/tests/fixtures/opportunities/phase3-resolution-cases.json
git add .gitattributes
git diff --cached --check
git commit -m "chore: stabilize fixed fixture line endings"
git push origin codex/phase-4-rules-eligibility-evaluation
```

Expected: staged diff only contains two `.gitattributes` lines；commit and push succeed。

### Task 1: Add proposed v0.4 contracts, schemas and example

**Files:**
- Create: `backend/src/deepaha/contracts/phase4.py`
- Modify: `backend/src/deepaha/contracts/__init__.py`
- Modify: `backend/src/deepaha/contracts/export.py`
- Create: `backend/tests/contracts/test_phase4_contracts.py`
- Create: `contracts/schemas/v0.4.0/rule-set.schema.json`
- Create: `contracts/schemas/v0.4.0/rule.schema.json`
- Create: `contracts/schemas/v0.4.0/rule-evidence.schema.json`
- Create: `contracts/schemas/v0.4.0/profile-snapshot.schema.json`
- Create: `contracts/schemas/v0.4.0/eligibility-result.schema.json`
- Create: `contracts/schemas/v0.4.0/match-snapshot.schema.json`
- Create: `contracts/schemas/v0.4.0/evaluation-run.schema.json`
- Create: `contracts/examples/v0.4.0/phase-4-example.json`
- Create: `docs/development/domain-contracts-v0.4.md`

**Interfaces:**
- Consumes: `ContractModel`, `EntityId`, `Instant`, `NonEmptyString`, `Sha256`, `VersionNumber`, `JsonValue` and v0.3 `OpportunityVersionSchemaV03` identifiers。
- Produces: `EvidenceAuthority`, `RuleOperator`, `RuleValueType`, `RuleOutcome`, `EligibilityStatus`, `RuleSetSchemaV04`, `RuleSchemaV04`, `RuleEvidenceSchemaV04`, `ProfileSnapshotSchemaV04`, `EligibilityResultSchemaV04`, `MatchSnapshotSchemaV04`, `EvaluationRunSchemaV04`。

- [ ] **Step 1: Write contract RED tests**

Add tests that import all produced names and assert:

```python
assert set(EligibilityStatus) == {
    EligibilityStatus.ELIGIBLE,
    EligibilityStatus.LIKELY_ELIGIBLE,
    EligibilityStatus.UNCERTAIN,
    EligibilityStatus.INELIGIBLE,
}
assert EvidenceAuthority.LATEST_OFFICIAL_CORRECTION.precedence == 600
assert EvidenceAuthority.LLM_SEMANTIC_INFERENCE.precedence == 100
```

Also validate these rejection cases with `pytest.raises(ValidationError)`:

```python
RuleEvidenceSchemaV04(authority="LLM_SEMANTIC_INFERENCE", precedence=300, ...)
EligibilityResultSchemaV04(status="INELIGIBLE", conflict_rule_ids=(), ...)
MatchSnapshotSchemaV04(input_sha256="0" * 64, rule_results=(), ...)
```

Snapshot the existing v0.1/v0.2/v0.3 schema tree before and after v0.4 export and assert every existing relative path and byte string is unchanged.

- [ ] **Step 2: Run tests to verify missing v0.4 imports fail**

Run:

```powershell
Push-Location backend
uv run pytest tests/contracts/test_phase4_contracts.py -q
Pop-Location
```

Expected: collection FAIL because `deepaha.contracts.phase4` does not exist。

- [ ] **Step 3: Implement the exact contract enums and validators**

Define the controlled operator and field vocabulary exactly:

```python
class RuleOperator(StrEnum):
    EQ = "EQ"
    NE = "NE"
    IN = "IN"
    NOT_IN = "NOT_IN"
    GTE = "GTE"
    LTE = "LTE"
    BETWEEN = "BETWEEN"
    CONTAINS_ANY = "CONTAINS_ANY"
    CONTAINS_ALL = "CONTAINS_ALL"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"
    AND = "AND"
    OR = "OR"
    NOT = "NOT"

class EligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    LIKELY_ELIGIBLE = "LIKELY_ELIGIBLE"
    UNCERTAIN = "UNCERTAIN"
    INELIGIBLE = "INELIGIBLE"
```

Use tuple fields and model validators to enforce unique stable IDs, official evidence for deterministic conflicts, exact evidence precedence, non-empty version identifiers, UTC instants, sorted deterministic content and a non-empty `rule_results` tuple for each MatchSnapshot.

- [ ] **Step 4: Extend deterministic export without touching older versions**

Add:

```python
PHASE4_SCHEMAS: dict[str, type[BaseModel]] = dict(PHASE3_SCHEMAS)
PHASE4_SCHEMAS.update({
    "rule-set.schema.json": RuleSetSchemaV04,
    "rule.schema.json": RuleSchemaV04,
    "rule-evidence.schema.json": RuleEvidenceSchemaV04,
    "profile-snapshot.schema.json": ProfileSnapshotSchemaV04,
    "eligibility-result.schema.json": EligibilityResultSchemaV04,
    "match-snapshot.schema.json": MatchSnapshotSchemaV04,
    "evaluation-run.schema.json": EvaluationRunSchemaV04,
})
```

`write_phase4_schemas()` must write only `contracts/schemas/v0.4.0` and CLI `--version` choices must become `("0.1.0", "0.2.0", "0.3.0", "0.4.0")`。

- [ ] **Step 5: Export schemas and add a fully synthetic example**

Run:

```powershell
Push-Location backend
uv run python -m deepaha.contracts.export .. --version 0.4.0
Pop-Location
```

The example must use IDs under `phase4-synthetic-*`, official-example URLs under `https://example.invalid/`, one deterministic official rule, one missing-field case, one MatchSnapshot and one EvaluationRun; it must explicitly declare `synthetic_only: true` in example metadata rather than imply real-world evidence.

- [ ] **Step 6: Document compatibility and candidate status**

`domain-contracts-v0.4.md` must state `PROPOSED` and `IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES`, list the seven new files, the four eligibility states, evidence precedence, version/replay fields, non-goals and the post-Gate closing-commit rebase requirement.

- [ ] **Step 7: Verify contracts, old bytes and repository quality**

Run:

```powershell
Push-Location backend
uv run pytest tests/contracts/test_phase1_contracts.py tests/contracts/test_phase2_contracts.py tests/contracts/test_phase3_contracts.py tests/contracts/test_phase4_contracts.py -q
uv run ruff check src/deepaha/contracts tests/contracts
uv run mypy src/deepaha/contracts tests/contracts
Pop-Location
git diff --check
```

Expected: all contract tests, Ruff and mypy PASS；`git diff -- contracts/schemas/v0.1.0 contracts/schemas/v0.2.0 contracts/schemas/v0.3.0` is empty。

- [ ] **Step 8: Commit and push**

Run:

```powershell
git add backend/src/deepaha/contracts backend/tests/contracts/test_phase4_contracts.py contracts/schemas/v0.4.0 contracts/examples/v0.4.0 docs/development/domain-contracts-v0.4.md
git diff --cached --check
git commit -m "feat: define proposed phase 4 contracts"
git push origin codex/phase-4-rules-eligibility-evaluation
```

### Task 2: Add versioned Phase 4 persistence

**Files:**
- Create: `backend/src/deepaha/rules/__init__.py`
- Create: `backend/src/deepaha/rules/models.py`
- Create: `backend/src/deepaha/profiles/__init__.py`
- Create: `backend/src/deepaha/profiles/models.py`
- Create: `backend/src/deepaha/eligibility/__init__.py`
- Create: `backend/src/deepaha/eligibility/models.py`
- Create: `backend/src/deepaha/matching/__init__.py`
- Create: `backend/src/deepaha/matching/models.py`
- Create: `backend/src/deepaha/evaluation/__init__.py`
- Create: `backend/src/deepaha/evaluation/models.py`
- Modify: `backend/src/deepaha/db/models.py`
- Create: `backend/migrations/versions/20260822_0004_phase4_rules_eligibility_evaluation.py`
- Create: `backend/tests/integration/test_phase4_persistence_contract.py`
- Create: `infra/compose.phase4.yaml`

**Interfaces:**
- Consumes: v0.4 enum string values, Phase 3 `opportunities`/`opportunity_versions`, existing `Base`, PostgreSQL JSONB and UUID/text timestamp conventions。
- Produces: ORM classes `RuleSetModel`, `RuleModel`, `RuleEvidenceModel`, `ProfileSnapshotModel`, `EligibilityResultModel`, `MatchSnapshotModel`, `MatchRuleResultModel`, `EvaluationRunModel`, `EvaluationCaseResultModel` and Alembic revision `20260822_0004`。

- [ ] **Step 1: Write migration and ORM RED tests**

Add an integration test which upgrades from `20260822_0003` to `head`, then asserts these exact tables exist:

```python
expected = {
    "rule_sets", "rules", "rule_evidence", "profile_snapshots",
    "eligibility_results", "match_snapshots", "match_rule_results",
    "evaluation_runs", "evaluation_case_results",
}
assert expected <= set(inspector.get_table_names())
```

Insert one complete synthetic graph, assert duplicate `(rule_set_id, version)` and duplicate `input_sha256` are rejected, and assert deleting referenced OpportunityVersion/RuleSet/ProfileSnapshot is restricted.

- [ ] **Step 2: Run the RED integration test against Phase 4 ports**

Run:

```powershell
$env:COMPOSE_PROJECT_NAME = 'deepaha-phase4-plan-task2'
docker compose -f infra/compose.phase4.yaml up -d --wait
Push-Location backend
$env:DEEPAHA_DATABASE_URL = 'postgresql+psycopg://deepaha:deepaha@127.0.0.1:55434/deepaha'
$env:DEEPAHA_S3_ENDPOINT_URL = 'http://127.0.0.1:55002'
uv run pytest tests/integration/test_phase4_persistence_contract.py -q -m integration
Pop-Location
```

Expected: FAIL because revision/table modules do not exist。Do not run `down`; leave lifecycle control to the Phase 4 verifier using the same isolated project name or a later unique `deepaha-phase4-*` name。

- [ ] **Step 3: Implement minimal ORM tables**

Use immutable/versioned columns and explicit constraints. The essential keys are:

```python
UniqueConstraint("rule_set_id", "version")
UniqueConstraint("profile_id", "version")
UniqueConstraint("input_sha256")
CheckConstraint("evidence_precedence IN (100, 200, 300, 400, 500, 600)")
CheckConstraint("status IN ('ELIGIBLE','LIKELY_ELIGIBLE','UNCERTAIN','INELIGIBLE')")
```

Store normalized DSL, profile facts, rule results and metric payload as JSONB while retaining relational FKs for `opportunity_version_id`, `rule_set_row_id`, `profile_snapshot_row_id`, `match_snapshot_id` and `evaluation_run_id`。Do not add update-in-place domain methods。

- [ ] **Step 4: Implement one additive migration**

Set:

```python
revision = "20260822_0004"
down_revision = "20260822_0003"
```

`upgrade()` creates only the nine Phase 4 tables and indexes; `downgrade()` drops only those tables in reverse dependency order。No SQL `UPDATE`, `DELETE` or Phase 1–3 table rewrite is permitted。

- [ ] **Step 5: Add isolated compose configuration**

Use service ports exactly:

```yaml
ports:
  - "55434:5432"
```

for PostgreSQL 18 and:

```yaml
ports:
  - "55002:5000"
```

for Moto S3, with Phase 4-specific container volume names generated through `COMPOSE_PROJECT_NAME`。

- [ ] **Step 6: Verify migration round trip and old persistence regressions**

Run:

```powershell
Push-Location backend
uv run alembic upgrade head
uv run pytest tests/integration/test_phase1_official_sample.py tests/integration/test_phase2_persistence_contract.py tests/integration/test_phase3_persistence_contract.py tests/integration/test_phase4_persistence_contract.py -q -m integration
uv run alembic downgrade 20260822_0003
uv run alembic upgrade head
uv run ruff check src/deepaha/rules src/deepaha/profiles src/deepaha/eligibility src/deepaha/matching src/deepaha/evaluation tests/integration/test_phase4_persistence_contract.py
uv run mypy src/deepaha/rules src/deepaha/profiles src/deepaha/eligibility src/deepaha/matching src/deepaha/evaluation tests/integration/test_phase4_persistence_contract.py
Pop-Location
```

Expected: migration and selected old/new persistence tests PASS；existing Phase 1–3 rows survive round trip。

- [ ] **Step 7: Commit and push**

Run:

```powershell
git add backend/src/deepaha/db/models.py backend/src/deepaha/rules backend/src/deepaha/profiles backend/src/deepaha/eligibility backend/src/deepaha/matching backend/src/deepaha/evaluation backend/migrations/versions/20260822_0004_phase4_rules_eligibility_evaluation.py backend/tests/integration/test_phase4_persistence_contract.py infra/compose.phase4.yaml
git diff --cached --check
git commit -m "feat: persist phase 4 evaluation history"
git push origin codex/phase-4-rules-eligibility-evaluation
```

### Task 3: Compile the minimal deterministic Rule DSL

**Files:**
- Create: `backend/src/deepaha/rules/types.py`
- Create: `backend/src/deepaha/rules/compiler.py`
- Modify: `backend/src/deepaha/rules/__init__.py`
- Create: `backend/tests/rules/__init__.py`
- Create: `backend/tests/rules/test_compiler.py`

**Interfaces:**
- Consumes: `RuleSchemaV04`, `RuleOperator`, `RuleValueType`。
- Produces: `RuleCompileError`, `FieldSpec`, `FIELD_REGISTRY`, `CompiledRule`, `CompiledRuleSet`, `compile_rule_set(rule_set: RuleSetSchemaV04) -> CompiledRuleSet`。

- [ ] **Step 1: Write compiler RED tests**

Construct one valid graph containing atomic `education_level GTE BACHELOR`, `certificates CONTAINS_ALL`, `birth_date BETWEEN`, and root `AND`。Assert deterministic topological order `("education", "certificate", "age", "root")` and equal `compiled_sha256` for repeated compilation。

Parametrize failures with exact reason codes:

```python
[
    ("UNKNOWN_OPERATOR", "unknown operator"),
    ("UNKNOWN_FIELD", "unknown field"),
    ("TYPE_MISMATCH", "type mismatch"),
    ("MISSING_OPERAND", "missing operand"),
    ("INVALID_ARITY", "invalid arity"),
    ("CYCLE", "cycle"),
    ("UNREACHABLE_RULE", "unreachable"),
]
```

- [ ] **Step 2: Run tests to verify imports fail**

Run:

```powershell
Push-Location backend
uv run pytest tests/rules/test_compiler.py -q
Pop-Location
```

Expected: FAIL because compiler module does not exist。

- [ ] **Step 3: Implement immutable compiled types and field registry**

Define:

```python
FIELD_REGISTRY = {
    "education_level": FieldSpec(RuleValueType.STRING, ordered=True),
    "major_code": FieldSpec(RuleValueType.STRING),
    "graduation_year": FieldSpec(RuleValueType.INTEGER, ordered=True),
    "student_status": FieldSpec(RuleValueType.STRING),
    "birth_date": FieldSpec(RuleValueType.DATE, ordered=True),
    "hukou_region": FieldSpec(RuleValueType.STRING),
    "residence_region": FieldSpec(RuleValueType.STRING),
    "target_regions": FieldSpec(RuleValueType.STRING_SET),
    "certificates": FieldSpec(RuleValueType.STRING_SET),
}
```

Use `@dataclass(frozen=True, slots=True)` for compiled objects and a stable JSON encoder with sorted keys/separators before SHA-256。

- [ ] **Step 4: Implement graph and type validation**

`compile_rule_set()` must:

1. Reject duplicate rule IDs and unknown root IDs.
2. Validate atomic versus composite shapes and exact arity (`NOT=1`, `AND/OR>=2`).
3. Validate each literal against the registered field type and operator matrix.
4. Traverse from root, detect a gray-node cycle, reject missing references and unreachable nodes.
5. Emit a stable topological tuple and hash from normalized JSON only。

It must not evaluate expressions, execute code, import user modules or accept arbitrary field paths。

- [ ] **Step 5: Verify compiler behavior and static quality**

Run:

```powershell
Push-Location backend
uv run pytest tests/rules/test_compiler.py -q
uv run ruff check src/deepaha/rules tests/rules
uv run mypy src/deepaha/rules tests/rules
Pop-Location
```

Expected: all compiler tests PASS。

- [ ] **Step 6: Commit and push**

Run:

```powershell
git add backend/src/deepaha/rules backend/tests/rules
git diff --cached --check
git commit -m "feat: compile deterministic eligibility rules"
git push origin codex/phase-4-rules-eligibility-evaluation
```

### Task 4: Add versioned major catalog and approved mapping match

**Files:**
- Create: `backend/src/deepaha/rules/major.py`
- Modify: `backend/src/deepaha/rules/__init__.py`
- Create: `backend/tests/rules/test_major.py`
- Create: `backend/tests/fixtures/evaluation/phase4-major-catalog.json`
- Create: `backend/tests/fixtures/evaluation/phase4-major-mapping.json`

**Interfaces:**
- Consumes: versioned JSON rows with `code`, `name`, `parent_codes`, source/provenance metadata and approved mapping `source_code -> target_code`。
- Produces: `MajorMatchKind`, `MajorMatchResult`, `MajorCatalog`, `ApprovedMajorMapping`, `match_major(profile_code: str | None, accepted_codes: tuple[str, ...], catalog: MajorCatalog, mapping: ApprovedMajorMapping, semantic_candidate: bool = False) -> MajorMatchResult`。

- [ ] **Step 1: Write professional-code RED tests**

Cover exact code, child-to-accepted-directory, approved mapping, semantic candidate, valid non-match, missing code, unknown catalog code and conflicting accepted codes。Exact expected kinds:

```python
EXACT, CATALOG, APPROVED_MAPPING, SEMANTIC_CANDIDATE,
NO_MATCH, MISSING, UNKNOWN_CODE, CONFLICT
```

Assert only exact/catalog/no-match are deterministic official conclusions, approved mapping is non-official support, and semantic candidate is never a pass/fail conclusion。

- [ ] **Step 2: Run tests to verify missing matcher fails**

Run:

```powershell
Push-Location backend
uv run pytest tests/rules/test_major.py -q
Pop-Location
```

Expected: FAIL because `rules.major` does not exist。

- [ ] **Step 3: Add fixed synthetic catalog and mapping assets**

Use a minimal synthetic hierarchy containing codes for computer science, software engineering, law and public administration. Every file must include:

```json
{
  "version": "phase4-synthetic-major-catalog-v1",
  "synthetic_only": true,
  "license": "CC0-1.0",
  "entries": []
}
```

The mapping file must additionally record `approved_by: "phase4-fixture-governance"` and `approved_at` as a fixed UTC instant。

- [ ] **Step 4: Implement strict loaders and matcher**

Loaders must reject duplicate codes, missing parents, catalog cycles, mapping cycles, unapproved rows and version mismatch。Matching order is exact → catalog ancestry → approved mapping → semantic candidate → deterministic no-match；missing/unknown/conflict short-circuit to their explicit kinds。

- [ ] **Step 5: Verify matcher and fixture byte determinism**

Run:

```powershell
Push-Location backend
uv run pytest tests/rules/test_major.py -q
uv run ruff check src/deepaha/rules tests/rules
uv run mypy src/deepaha/rules tests/rules
Pop-Location
git ls-files --eol backend/tests/fixtures/evaluation/*.json
```

Expected: tests/static checks PASS；fixtures show `w/lf attr/text eol=lf` after staging/checkout materialization。

- [ ] **Step 6: Commit and push**

Run:

```powershell
git add backend/src/deepaha/rules backend/tests/rules/test_major.py backend/tests/fixtures/evaluation/phase4-major-catalog.json backend/tests/fixtures/evaluation/phase4-major-mapping.json
git diff --cached --check
git commit -m "feat: match versioned major codes"
git push origin codex/phase-4-rules-eligibility-evaluation
```

### Task 5: Evaluate deterministic rules into protected eligibility states

**Files:**
- Create: `backend/src/deepaha/eligibility/engine.py`
- Modify: `backend/src/deepaha/eligibility/__init__.py`
- Create: `backend/tests/eligibility/__init__.py`
- Create: `backend/tests/eligibility/test_engine.py`

**Interfaces:**
- Consumes: `CompiledRuleSet`, profile fact mapping, opportunity fact mapping, `RuleEvidenceSchemaV04`, `MajorCatalog`, `ApprovedMajorMapping`, fixed scenario clock。
- Produces: `EvaluationContext`, `EvaluatedRule`, `EligibilityDecision`, `evaluate_eligibility(context: EvaluationContext) -> EligibilityDecision`。

- [ ] **Step 1: Write four-state and boundary RED tests**

Add exact scenarios:

```python
assert evaluate(case_all_official_pass).status is EligibilityStatus.ELIGIBLE
assert evaluate(case_approved_mapping_pass).status is EligibilityStatus.LIKELY_ELIGIBLE
assert evaluate(case_missing_certificate).status is EligibilityStatus.UNCERTAIN
assert evaluate(case_official_degree_conflict).status is EligibilityStatus.INELIGIBLE
```

Also assert:

- age uses the fixed scenario clock and birth-date boundary, not wall-clock time;
- `graduation_year` and `student_status` contradictions become `UNCERTAIN` when official rules conflict;
- missing hukou/residence/certificate never becomes `INELIGIBLE`;
- semantic major candidate never exceeds `UNCERTAIN`;
- a deterministic conflict with precedence 100/200 is downgraded to `UNCERTAIN`;
- `INELIGIBLE` contains at least one official conflict rule ID and its EvidenceRef。

- [ ] **Step 2: Run tests to verify engine is absent**

Run:

```powershell
Push-Location backend
uv run pytest tests/eligibility/test_engine.py -q
Pop-Location
```

Expected: FAIL because engine module does not exist。

- [ ] **Step 3: Implement atomic evaluators without dynamic execution**

Dispatch through an explicit mapping:

```python
ATOMIC_EVALUATORS = {
    RuleOperator.EQ: _evaluate_eq,
    RuleOperator.NE: _evaluate_ne,
    RuleOperator.IN: _evaluate_in,
    RuleOperator.NOT_IN: _evaluate_not_in,
    RuleOperator.GTE: _evaluate_gte,
    RuleOperator.LTE: _evaluate_lte,
    RuleOperator.BETWEEN: _evaluate_between,
    RuleOperator.CONTAINS_ANY: _evaluate_contains_any,
    RuleOperator.CONTAINS_ALL: _evaluate_contains_all,
    RuleOperator.EXISTS: _evaluate_exists,
    RuleOperator.NOT_EXISTS: _evaluate_not_exists,
}
```

Return `SATISFIED`, `CONFLICT`, or `UNKNOWN` plus reason code and exact evidence IDs。No `eval`, expression parser, model call or ranking score is allowed。

- [ ] **Step 4: Implement composite truth table and final aggregation**

Use three-valued composition:

```text
AND: any CONFLICT -> CONFLICT; else any UNKNOWN -> UNKNOWN; else SATISFIED
OR: any SATISFIED -> SATISFIED; else any UNKNOWN -> UNKNOWN; else CONFLICT
NOT: SATISFIED <-> CONFLICT; UNKNOWN -> UNKNOWN
```

Final aggregation order:

1. Any deterministic conflict with precedence >=300 and official EvidenceRef → `INELIGIBLE`.
2. Any missing/ambiguous/conflicting evidence, unknown result, or semantic-only result → `UNCERTAIN`.
3. Any positive conclusion depending on precedence 200 approved mapping → `LIKELY_ELIGIBLE`.
4. Otherwise every required rule is official and satisfied → `ELIGIBLE`。

- [ ] **Step 5: Verify engine and negative-kill protection**

Run:

```powershell
Push-Location backend
uv run pytest tests/eligibility/test_engine.py -q
uv run ruff check src/deepaha/eligibility tests/eligibility
uv run mypy src/deepaha/eligibility tests/eligibility
Pop-Location
```

Expected: all engine tests PASS；no missing or low-authority case produces `INELIGIBLE`。

- [ ] **Step 6: Commit and push**

Run:

```powershell
git add backend/src/deepaha/eligibility backend/tests/eligibility
git diff --cached --check
git commit -m "feat: evaluate protected eligibility states"
git push origin codex/phase-4-rules-eligibility-evaluation
```

### Task 6: Persist deterministic MatchSnapshot and replay differences

**Files:**
- Create: `backend/src/deepaha/eligibility/service.py`
- Modify: `backend/src/deepaha/eligibility/__init__.py`
- Create: `backend/tests/integration/test_phase4_match_replay.py`

**Interfaces:**
- Consumes: `Session`, `OpportunityVersionModel`, `RuleSetModel`, `ProfileSnapshotModel`, compiled rule set, catalog/mapping versions, scenario clock and `evaluate_eligibility()`。
- Produces: `MatchInput`, `ReplayDifference`, `EligibilityService.evaluate_and_save(match_input: MatchInput) -> MatchSnapshotSchemaV04`, `EligibilityService.replay(match_snapshot_id: str) -> MatchSnapshotSchemaV04`, `EligibilityService.diff(left_id: str, right_id: str) -> tuple[ReplayDifference, ...]`。

- [ ] **Step 1: Write service RED integration tests**

Persist one opportunity version, rule set and profile snapshot。Assert:

```python
first = service.evaluate_and_save(match_input)
second = service.evaluate_and_save(match_input)
assert first.match_snapshot_id == second.match_snapshot_id
assert first.input_sha256 == second.input_sha256
assert service.replay(first.match_snapshot_id).model_dump() == first.model_dump()
```

Change only `scenario_clock`, `profile_snapshot_id`, `rule_set_id`, `catalog_version`, and `mapping_version` in separate cases and assert `diff()` names exactly that version/input field plus any downstream rule-result changes。

- [ ] **Step 2: Run test to verify service is absent**

Run:

```powershell
Push-Location backend
uv run pytest tests/integration/test_phase4_match_replay.py -q -m integration
Pop-Location
```

Expected: FAIL because `EligibilityService` does not exist。

- [ ] **Step 3: Implement canonical MatchInput hashing**

Hash a normalized payload containing only:

```python
{
    "opportunity_version_id": ...,
    "rule_set_id": ...,
    "rule_set_version": ...,
    "profile_snapshot_id": ...,
    "profile_version": ...,
    "engine_version": ...,
    "catalog_version": ...,
    "mapping_version": ...,
    "scenario_clock": ...,
    "compiled_rule_set_sha256": ...,
}
```

Serialize with sorted keys and fixed separators; no database row timestamp or wall-clock value enters the hash。

- [ ] **Step 4: Implement transactional idempotency and replay**

Look up `input_sha256` before evaluation; on a uniqueness race, roll back and read the existing row。Save EligibilityResult, MatchSnapshot and ordered MatchRuleResult rows in one transaction。Replay reconstructs from saved rows and refuses current-config substitution。Diff compares exact version/input fields, status, per-rule outcome/reason/evidence IDs。

- [ ] **Step 5: Verify integration replay and old Phase 3 behavior**

Run:

```powershell
Push-Location backend
uv run pytest tests/integration/test_phase4_match_replay.py tests/integration/test_phase3_resolution_replay.py -q -m integration
uv run ruff check src/deepaha/eligibility tests/integration/test_phase4_match_replay.py
uv run mypy src/deepaha/eligibility tests/integration/test_phase4_match_replay.py
Pop-Location
```

Expected: replay/idempotency/diff and Phase 3 replay PASS。

- [ ] **Step 6: Commit and push**

Run:

```powershell
git add backend/src/deepaha/eligibility backend/tests/integration/test_phase4_match_replay.py
git diff --cached --check
git commit -m "feat: save replayable match snapshots"
git push origin codex/phase-4-rules-eligibility-evaluation
```

### Task 7: Generate the fixed Golden Dataset and 20/100 synthetic profiles

**Files:**
- Create: `backend/tests/fixtures/evaluation/generate_phase4_fixtures.py`
- Create: `backend/tests/fixtures/evaluation/phase4-golden-cases.json`
- Create: `backend/tests/fixtures/evaluation/phase4-mother-profiles.json`
- Create: `backend/tests/fixtures/evaluation/phase4-synthetic-profiles.json`
- Create: `backend/tests/fixtures/evaluation/phase4-fixtures.manifest.json`
- Create: `backend/src/deepaha/evaluation/fixtures.py`
- Modify: `backend/src/deepaha/evaluation/__init__.py`
- Create: `backend/tests/evaluation/__init__.py`
- Create: `backend/tests/evaluation/test_fixtures.py`

**Interfaces:**
- Consumes: v0.4 ProfileSnapshot and Golden case contract shapes, fixed catalog/mapping files。
- Produces: `FixtureBundle`, `load_fixture_bundle(directory: Path) -> FixtureBundle`, `verify_fixture_manifest(directory: Path) -> None` plus exactly 20 mother and 100 derived profile snapshots。

- [ ] **Step 1: Write fixture RED tests**

Assert:

```python
assert len(bundle.mother_profiles) == 20
assert len(bundle.synthetic_profiles) == 100
assert {p.mother_profile_id for p in bundle.synthetic_profiles} == {
    p.profile_id for p in bundle.mother_profiles
}
assert all(p.synthetic_only for p in bundle.mother_profiles + bundle.synthetic_profiles)
```

Require Golden coverage tags exactly include:

```python
{
    "age-boundary", "missing-field", "evidence-conflict",
    "major-exact", "major-catalog", "major-approved-mapping",
    "major-semantic-candidate", "education", "graduation-status",
    "hukou-region", "certificate", "false-negative-protection",
}
```

Tamper with a copied fixture byte and assert manifest verification fails before parsing。

- [ ] **Step 2: Run test to verify fixtures are missing**

Run:

```powershell
Push-Location backend
uv run pytest tests/evaluation/test_fixtures.py -q
Pop-Location
```

Expected: FAIL because fixture loader/files do not exist。

- [ ] **Step 3: Implement deterministic generator**

Use fixed constants:

```python
GENERATOR_VERSION = "phase4-fixture-generator-v1"
SCENARIO_CLOCK = "2026-08-22T00:00:00Z"
MOTHER_COUNT = 20
DERIVED_PER_MOTHER = 5
```

Generate IDs from stable string hashes, not random UUIDs。Each derived profile changes one declared fact from its mother and records `variation_axis`。No name, phone, email, school person record or real user data is allowed。

- [ ] **Step 4: Generate and verify manifest**

Run:

```powershell
Push-Location backend
uv run python tests/fixtures/evaluation/generate_phase4_fixtures.py
Pop-Location
```

The manifest must include every Phase 4 evaluation JSON filename, SHA-256, byte length, record count, `license: "CC0-1.0"`, `synthetic_only: true`, generator version and fixed scenario clock。The generator must reproduce byte-identical output on a second run。

- [ ] **Step 5: Implement strict loader and rerun determinism checks**

Load JSON only after verifying all manifest bytes。Reject undeclared JSON files, missing files, duplicate IDs, non-synthetic profile rows, profile-version collisions and a derived profile without an existing mother。

Run:

```powershell
Push-Location backend
$before = Get-FileHash tests/fixtures/evaluation/*.json -Algorithm SHA256
uv run python tests/fixtures/evaluation/generate_phase4_fixtures.py
$after = Get-FileHash tests/fixtures/evaluation/*.json -Algorithm SHA256
Compare-Object ($before | Sort-Object Path | ForEach-Object Hash) ($after | Sort-Object Path | ForEach-Object Hash)
uv run pytest tests/evaluation/test_fixtures.py -q
Pop-Location
```

Expected: `Compare-Object` produces no output；tests PASS。

- [ ] **Step 6: Verify quality, commit and push**

Run:

```powershell
Push-Location backend
uv run ruff check src/deepaha/evaluation tests/evaluation tests/fixtures/evaluation/generate_phase4_fixtures.py
uv run mypy src/deepaha/evaluation tests/evaluation tests/fixtures/evaluation/generate_phase4_fixtures.py
Pop-Location
git diff --check
git add backend/src/deepaha/evaluation backend/tests/evaluation backend/tests/fixtures/evaluation
git diff --cached --check
git commit -m "test: add phase 4 synthetic evaluation fixtures"
git push origin codex/phase-4-rules-eligibility-evaluation
```

### Task 8: Run and persist synthetic evaluation replay

**Files:**
- Create: `backend/src/deepaha/evaluation/runner.py`
- Modify: `backend/src/deepaha/evaluation/__init__.py`
- Create: `backend/tests/evaluation/test_runner.py`
- Create: `backend/tests/integration/test_phase4_evaluation_run.py`

**Interfaces:**
- Consumes: `FixtureBundle`, `EligibilityService`, fixed opportunity/rule-set fixtures and scenario clock。
- Produces: `EvaluationMetrics`, `EvaluationReport`, `run_synthetic_evaluation(bundle: FixtureBundle, evaluator: CaseEvaluator) -> EvaluationReport`, `persist_evaluation_run(session: Session, report: EvaluationReport) -> EvaluationRunSchemaV04`。

- [ ] **Step 1: Write runner RED tests**

Use a deterministic fake evaluator and assert exact metric formulas:

```python
assert metrics.case_count == len(cases)
assert metrics.expected_ineligible_count == expected_ineligible
assert metrics.actual_ineligible_count == actual_ineligible
assert metrics.unexpected_ineligible_count == 0
assert metrics.unexpected_ineligible_case_ids == ()
```

Assert the report labels evidence as `SYNTHETIC_EVALUATION_ONLY`, includes dataset/catalog/mapping/rule/engine versions, and does not contain `production_accuracy`, `retention`, `willingness_to_pay` or a computed `0.5%` claim。

- [ ] **Step 2: Run tests to verify runner is missing**

Run:

```powershell
Push-Location backend
uv run pytest tests/evaluation/test_runner.py tests/integration/test_phase4_evaluation_run.py -q
Pop-Location
```

Expected: FAIL because evaluation runner does not exist。

- [ ] **Step 3: Implement deterministic batch runner**

Sort cases by stable case ID。For each case record expected status, actual status, `unexpected_ineligible`, input hash and MatchSnapshot ID。Metrics are integer counts and explicit case-ID tuples; no percentage is labeled as real accuracy。Raise `UnexpectedIneligibleError` when any protected case unexpectedly returns `INELIGIBLE`。

- [ ] **Step 4: Persist immutable run and case rows**

Persist input manifest SHA, dataset/catalog/mapping/rule/engine versions, scenario clock, started/completed instants supplied by the caller, metric JSON, evidence label and ordered case results。Replaying the same version tuple must produce the same report digest, while run IDs may differ only when caller explicitly requests a separate audit run。

- [ ] **Step 5: Verify unit/integration replay and zero unexpected negatives**

Run:

```powershell
Push-Location backend
uv run pytest tests/evaluation/test_runner.py tests/integration/test_phase4_evaluation_run.py -q
uv run ruff check src/deepaha/evaluation tests/evaluation tests/integration/test_phase4_evaluation_run.py
uv run mypy src/deepaha/evaluation tests/evaluation tests/integration/test_phase4_evaluation_run.py
Pop-Location
```

Expected: tests/static checks PASS；fixed evaluation reports zero unexpected `INELIGIBLE` and remains explicitly synthetic-only。

- [ ] **Step 6: Commit and push**

Run:

```powershell
git add backend/src/deepaha/evaluation backend/tests/evaluation/test_runner.py backend/tests/integration/test_phase4_evaluation_run.py
git diff --cached --check
git commit -m "feat: replay synthetic eligibility evaluation"
git push origin codex/phase-4-rules-eligibility-evaluation
```

### Task 9: Add Phase 4 verifier, CI and blocked Gate evidence

**Files:**
- Create: `scripts/verify-phase4.ps1`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/development/README.md`
- Modify: `docs/development/system-roadmap.md`
- Modify: `docs/development/architecture.md`
- Modify: `docs/development/quality-and-release.md`
- Create: `docs/gates/phase-4/README.md`
- Create: `docs/gates/phase-4/acceptance-results.md`
- Create: `docs/gates/phase-4/test-summary.md`
- Create: `docs/gates/phase-4/evaluation-summary.md`
- Create: `docs/gates/phase-4/security-and-compliance.md`
- Create: `docs/gates/phase-4/deferred-decisions.md`
- Create: `docs/gates/phase-4/operations.md`
- Create: `backend/tests/test_phase4_verifier_scope.py`

**Interfaces:**
- Consumes: all Phase 4 tests/fixtures, `infra/compose.phase4.yaml`, Phase 2/3 Gate facts。
- Produces: `scripts/verify-phase4.ps1` with isolated project/ports and a GitHub Actions Phase 4 job; evidence documents with maximum status `IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES`。

- [ ] **Step 1: Write verifier-scope RED tests**

Parse verifier, compose and CI text and assert:

```python
assert "55434" in compose_text and "55002" in compose_text
assert "55432" not in verifier_text and "55000" not in verifier_text
assert "55433" not in verifier_text and "55001" not in verifier_text
assert "deepaha-phase2-live-gate" not in verifier_text
assert "IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES" in gate_readme
```

Assert the verifier never calls live-source, browser, model, Phase 2 observation or Phase 1/2/3 scoped verifier scripts。

- [ ] **Step 2: Run test to verify verifier/evidence are absent**

Run:

```powershell
Push-Location backend
uv run pytest tests/test_phase4_verifier_scope.py -q
Pop-Location
```

Expected: FAIL because Phase 4 verifier and Gate directory do not exist。

- [ ] **Step 3: Implement the isolated verifier**

The script must:

1. Require Docker and `uv`.
2. Generate or accept a `COMPOSE_PROJECT_NAME` beginning `deepaha-phase4-`.
3. Reject occupied 55434/55002 before startup unless the process belongs to its exact Phase 4 project.
4. Start only `infra/compose.phase4.yaml` and wait for health.
5. Set Phase 4 DB/S3 environment variables.
6. Run schema-byte checks, fixture manifest checks, Ruff, mypy, unit tests and Phase 4 integration tests.
7. Print the exact synthetic evaluation summary and blocked candidate status.
8. In `finally`, stop/remove only its exact Phase 4 project resources; never reference Phase 2/3 project names or ports。

- [ ] **Step 4: Add a Phase 4 scoped CI job**

Trigger on `codex/phase-4-rules-eligibility-evaluation` and pull requests touching Phase 4 paths。Use PostgreSQL 18 and Moto service ports mapped to 55434/55002。Run the same non-live commands as the local verifier and upload only text/JUnit evidence if existing CI patterns already upload artifacts；do not upload DB volumes, S3 objects or source fixtures as new public artifacts。

- [ ] **Step 5: Write truthful Gate and development documentation**

Every Phase 4 Gate file must distinguish:

- `implemented`: code exists on an exact candidate SHA;
- `locally verified`: exact commands/results recorded after final run;
- `remote CI`: initially pending, later updated with exact run/job URLs and conclusions;
- `synthetic evaluation`: zero unexpected negatives only within fixed synthetic fixtures;
- `blocked`: Phase 2 `OPEN`, Phase 3 `BLOCKED_BY_PHASE2`, v0.2/v0.3/v0.4 `PROPOSED`。

`deferred-decisions.md` must list real annotated evaluation, `<=0.5%` proof, LLM, Phase 5/6, live users/UI/API and release as deferred。`operations.md` must give exact post-Gate update/reverify commands without touching live Phase 2 observation。

- [ ] **Step 6: Run the Phase 4 verifier and root regression**

Run:

```powershell
& ./scripts/verify-phase4.ps1
& ./scripts/verify.ps1
```

Expected: both PASS；Phase 4 output says synthetic-only and `IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES`。

- [ ] **Step 7: Run scope, secret and artifact review**

Run:

```powershell
git diff --check
git status --short
rg -n --hidden -g '!\.git/**' -g '!backend/.venv/**' '(BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|password\s*[:=]\s*[^<])' .
git status --short | Select-String -Pattern '\.(db|sqlite|sqlite3|pyc|log|zip|tar|gz)$|__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|cookie|token|secret'
git diff --name-only 5a5847be266980e83eccd8718c23b77e788ee481...HEAD
```

Expected: no secret finding, no prohibited artifact, and every changed path maps to Phase 4/spec/plan or the Task 0 line-ending rule。

- [ ] **Step 8: Commit and push candidate evidence**

Run:

```powershell
git add scripts/verify-phase4.ps1 .github/workflows/ci.yml docs/development docs/gates/phase-4 backend/tests/test_phase4_verifier_scope.py
git diff --cached --check
git commit -m "ci: verify blocked phase 4 candidate"
git push origin codex/phase-4-rules-eligibility-evaluation
```

### Task 10: Verify the pushed candidate, create draft PR and record remote CI

**Files:**
- Modify: `docs/gates/phase-4/test-summary.md`
- Modify: `docs/gates/phase-4/acceptance-results.md`
- Modify: `docs/gates/phase-4/README.md`

**Interfaces:**
- Consumes: pushed Phase 4 candidate SHA, GitHub Actions and stacked base branch。
- Produces: clean branch, exact candidate SHA, stacked draft PR, successful remote CI references and final blocked status。

- [ ] **Step 1: Run final local verification from the exact pushed SHA**

Run:

```powershell
git fetch origin
$candidateSha = git rev-parse HEAD
if ((git rev-parse origin/codex/phase-4-rules-eligibility-evaluation) -ne $candidateSha) { throw 'remote head mismatch' }
if (-not (git merge-base --is-ancestor 5a5847be266980e83eccd8718c23b77e788ee481 $candidateSha)) { throw 'base is not ancestor' }
& ./scripts/verify-phase4.ps1
& ./scripts/verify.ps1
git status --short
```

Expected: remote and local SHA match, both verifiers PASS, status clean。

- [ ] **Step 2: Create or update the stacked draft PR**

Run:

```powershell
gh pr create --draft --base codex/phase-3-opportunity-resolution --head codex/phase-4-rules-eligibility-evaluation --title "Phase 4: rules, eligibility and evaluation" --body-file docs/gates/phase-4/README.md
```

If a PR already exists, use `gh pr edit <number> --base codex/phase-3-opportunity-resolution --title ... --body-file ...` and verify `isDraft=true`, `state=OPEN`, base/head exact, merge not performed。

- [ ] **Step 3: Wait for and inspect remote CI**

Run:

```powershell
gh run list --branch codex/phase-4-rules-eligibility-evaluation --limit 10
gh pr checks <phase4-pr-number> --watch --interval 30
```

Expected: every required Phase 4 candidate job reaches `success`。On failure, invoke `superpowers:systematic-debugging`, inspect `gh run view <run-id> --log-failed`, fix through a new RED/tested commit, push, and wait for the replacement run。

- [ ] **Step 4: Record exact local and remote evidence without closing Gates**

Update evidence files with:

```text
Candidate SHA: <exact 40-character SHA>
Local root verification: PASS at <UTC instant>
Local Phase 4 verification: PASS at <UTC instant>
Remote workflow run: <exact run ID and URL>
Required jobs: <job name>=success
Draft PR: <number and URL>, OPEN/DRAFT/UNMERGED
Status: IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES
```

Keep the synthetic evaluation wording scoped to fixed fixtures and keep Phase 2/3/v0.2/v0.3/v0.4 statuses unchanged。

- [ ] **Step 5: Verify evidence-only diff, commit and wait for final evidence CI**

Run:

```powershell
git diff --check
git diff -- docs/gates/phase-4
git add docs/gates/phase-4
git diff --cached --check
git commit -m "docs: record phase 4 candidate verification"
git push origin codex/phase-4-rules-eligibility-evaluation
gh pr checks <phase4-pr-number> --watch --interval 30
```

Expected: evidence commit push succeeds and its required jobs all reach `success`。

- [ ] **Step 6: Perform final branch audit**

Run:

```powershell
git fetch origin
git status --short
git rev-parse HEAD
git rev-parse origin/codex/phase-4-rules-eligibility-evaluation
git log --oneline --decorate 5a5847be266980e83eccd8718c23b77e788ee481..HEAD
gh pr view <phase4-pr-number> --json number,url,state,isDraft,baseRefName,headRefName,mergeStateStatus,statusCheckRollup
```

Expected: worktree clean；local/remote SHA exact match；PR remains OPEN/DRAFT/UNMERGED with base Phase 3 and head Phase 4；final status remains `IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES`。

- [ ] **Step 7: Record the mandatory post-Phase2/3 rebase and full re-verification procedure**

The handoff must state that after both upstream Gates close:

1. Fetch the exact Phase 2 and Phase 3 closing commits.
2. Review v0.2/v0.3 Schema bytes, migrations, identifiers, evidence semantics and replay behavior against Phase 4 assumptions.
3. Rebase/update Phase 4 to the exact Phase 3 closing commit without rewriting Phase 2/3 worktrees.
4. Re-export v0.4 only, rerun all contract byte checks, root verifier, Phase 4 verifier, migration round trip, fixed synthetic evaluation, scope/secret/artifact review and remote CI.
5. Update candidate evidence through a new reviewed commit; do not mark STABLE or close Phase 4 Gate unless separate Gate authority and real evidence exist。

## Plan Self-Review Record

- **Spec coverage:** Tasks 1–8 cover v0.4 contracts, additive persistence, bounded DSL/compiler, four-state engine,专业/学历/毕业/年龄/户籍/证书/缺失规则、MatchSnapshot、20/100 合成画像、Golden Dataset、EvaluationRun 与错误否定保护；Tasks 9–10 cover verifier、CI、Gate evidence、stacked draft PR and post-Gate re-verification。
- **Boundary coverage:** Global constraints and verifier tests prohibit Phase 2/3 worktree/project/port access, live observation, LLM/browser/network tests, UI/API/ranking and release/Gate promotion。
- **Placeholder scan:** The plan contains exact paths, signatures, test assertions, commands and expected outcomes; no unspecified implementation step remains。
- **Type consistency:** `RuleSchemaV04 -> compile_rule_set() -> CompiledRuleSet -> evaluate_eligibility() -> EligibilityDecision -> EligibilityService -> MatchSnapshotSchemaV04 -> EvaluationReport -> EvaluationRunSchemaV04` is the single declared flow used by later tasks。
- **Execution selection:** The user explicitly required no subagents and continuous work, so the only permitted execution path is inline `superpowers:executing-plans` in this session。
