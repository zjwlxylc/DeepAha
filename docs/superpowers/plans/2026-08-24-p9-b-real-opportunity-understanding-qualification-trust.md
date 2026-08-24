# P9-B Real Opportunity Understanding & Qualification Trust Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立从 P9-A VALID 官方证据到可定位文档块、候选事实、独立验证、版本化事实、规则候选、受控编译及资格基准的可审计工程链，同时在缺少真实独立人工 Gold 时保持明确的 `NOT_OBSERVED` 边界。

**Architecture:** 在现有 Phase 3 `opportunity_id + opportunity_version:int`、Phase 4 legacy RuleSet/Eligibility 和 P9-A acquisition provenance 旁新增 P9-B 数据层，不改写历史表或读取语义。每个 Slice 通过 additive migration、不可变模型、TDD、PostgreSQL 约束和独立 verifier 闭合；Gold/Benchmark 与生产事实物理隔离，外部模型只能产生 Candidate，并且必须先通过逐次 Data/Content Egress Gate。

**Tech Stack:** Python 3.14、Pydantic 2、SQLAlchemy 2、Alembic、PostgreSQL 18、pytest、JSON Schema、PowerShell verifier、现有 S3-compatible object store、provider-neutral HTTP gateway。

**Spec:** `docs/gates/p9-b/P9B_ARCHITECTURE_CLOSURE.md`（Task 1 建立；外部原件仅只读输入）

## Global Constraints

- 起始 Git 基线为 `f27f096db1d7028305d4e5989360fde68b578678`，直接 parent 为 `94741c19a3a8471866930a46f7e70d85b7e79a68`；当前为 Codex App 管理的 detached linked worktree，不创建嵌套 worktree。
- P9-A 保持 `Independent Revalidation=PASS / P0=0 / P1=0 / P2=0 / Engineering Gate=CLOSED / Release Qualification=NOT_STARTED / 100-source/14-day=NOT_RUN / Contract=IMPLEMENTED, not STABLE`。
- OpportunityVersion 身份只使用 `opportunity_id + opportunity_version:int`；禁止引入不存在的 `opportunity_version_id`。
- 所有 migration 均 forward/additive；不得重写 `20260821_0001` 至 `20260823_0010`。
- Stage 1 不改变 legacy RuleSet、Eligibility、Public Catalog、Personal Action、Ranking、Notification、Feedback 的读取路径。
- Gold 与生产事实隔离；模型输出只能是 Candidate；Unit rule 不得进入父 Opportunity RuleSet；`INELIGIBLE` 仍需确定性冲突规则和官方 Evidence。
- 生产资格状态仅为 `ELIGIBLE / LIKELY_ELIGIBLE / UNCERTAIN / INELIGIBLE`；`UNKNOWN` 是事实/抽取/abstention 状态，`NEEDS_MORE_INFO` 只能是 `UNCERTAIN` reason code。
- Semantic Cache 保持 `DISABLED`，直到 identity binding 与 dependency invalidation Gate 通过。
- 不伪造 Gold、Annotator、Verifier、Adjudicator、Curator、provider cost 或 provenance；缺失证据记录 `NOT_OBSERVED`/`NOT_RUN`。
- 不 push、不 merge、不 deploy、不启动 Release Qualification、不自动联系机构或真人。

---

### Task 0: Freeze Baseline and Start the Implementation Ledger

**Files:**
- Create: `docs/gates/p9-b/P9B_IMPLEMENTATION_LEDGER.md`
- Modify: `docs/superpowers/plans/2026-08-24-p9-b-real-opportunity-understanding-qualification-trust.md`

**Interfaces:**
- Consumes: Git baseline facts and the user-approved Slice order.
- Produces: append-only human-readable ledger entries containing Slice, base/head, exact commands, outcomes, review findings and commit SHA.

- [x] **Step 1: Record the pre-change evidence**

  Record exact HEAD/parent/detached/worktree/status and the observed baseline `uv run pytest` result (`627 passed, 274 deselected`).

- [x] **Step 2: Validate the plan and ledger prose**

  Run: `$patterns = @([string]::Concat('T','BD'), [string]::Concat('T','ODO'), [string]::Concat('IMPLEMENTED_','PENDING')); Select-String -Pattern $patterns -Path docs/superpowers/plans/2026-08-24-p9-b-real-opportunity-understanding-qualification-trust.md,docs/gates/p9-b/P9B_IMPLEMENTATION_LEDGER.md`

  Expected: no match. Separately scan `opportunity_version_id`; every match must explicitly prohibit or reject that nonexistent identity.

- [x] **Step 3: Commit the planning baseline**

  Run: `git add docs/superpowers/plans/2026-08-24-p9-b-real-opportunity-understanding-qualification-trust.md docs/gates/p9-b/P9B_IMPLEMENTATION_LEDGER.md && git commit -m "docs: plan P9-B qualification trust"`

### Task 1: P9-B0 Architecture Closure, Canonical Hash Contract and Versioned Schemas

**Files:**
- Create: `docs/gates/p9-b/P9B_ARCHITECTURE_CLOSURE.md`
- Create: `backend/src/deepaha/p9b/__init__.py`
- Create: `backend/src/deepaha/p9b/hashing.py`
- Create: `backend/src/deepaha/contracts/phase9b.py`
- Create: `backend/tests/p9b/test_hashing.py`
- Create: `backend/tests/contracts/test_phase9b_contracts.py`
- Create: `contracts/schemas/v0.8.0/*.schema.json`
- Create: `contracts/examples/v0.8.0/p9-b0-example.json`
- Modify: `backend/src/deepaha/contracts/export.py`
- Modify: `backend/src/deepaha/contracts/__init__.py`

**Interfaces:**
- Consumes: external Gold/Benchmark v1.2 SHA-256 `8D4ECE8B2638768358D43F37F70762B6E5F85E1360F5F7E9DE19C67FDFBDB6CC`, ADR v1.1 SHA-256 `CB9FECEDF5AA8AB2C0199C11266E20F4343C492135543E4361E5FB4099E64552`, current v0.3 OpportunityVersion and v0.4 RuleSet contracts.
- Produces: `canonical_hash(domain: HashDomain, payload: object) -> str`, `document_parse_key(...) -> str`, `canonical_bundle_hash(...) -> str`, `split_manifest_hash(...) -> str`, plus strict v0.8 Pydantic/JSON schemas.

- [x] **Step 1: Write RED canonical-hash golden-vector tests**

  Tests must hand-specify UTF-8 bytes and expected SHA-256 for domain-separated canonical JSON with lexicographically sorted object fields, array-order preservation, explicit JSON `null`, no NaN/Infinity, and hash-contract version `p9b-canonical-json-sha256-v1`.

- [x] **Step 2: Run RED tests**

  Run: `uv run pytest tests/p9b/test_hashing.py -q`

  Expected: FAIL because `deepaha.p9b.hashing` does not exist.

- [x] **Step 3: Implement the minimal canonical serializer and hash functions**

  Use `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)` encoded as UTF-8 and prepend `deepaha:p9b:<domain>:p9b-canonical-json-sha256-v1\0`. Hash inputs are explicit mappings; UUID/datetime conversion occurs before hashing in typed contract methods, never through implicit `default=str`.

- [x] **Step 4: Write RED contract tests**

  Cover the real composite OpportunityVersion identity, strict enums, Unit/Bundle/Member/Parse/Dataset manifest shapes, exact expected entry counts `30/70/30/200`, separate `atomic_group_count`, answer access, cutoff, invalidation/successor and rejection of extra fields or `opportunity_version_id`.

- [x] **Step 5: Run RED contract tests**

  Run: `uv run pytest tests/contracts/test_phase9b_contracts.py -q`

  Expected: FAIL because v0.8 contracts/export do not exist.

- [x] **Step 6: Implement and export v0.8 contracts**

  Add the smallest strict Pydantic models and checked-in JSON schemas needed by B0. Existing version directories remain byte-for-byte unchanged.

- [x] **Step 7: Write the unique Architecture Closure**

  Record external version/path/hash, current repository precedence, the composite OpportunityVersion correction, Unit transition rules, member-level provenance, parse contract identity, exact partitions, canonicalization, B0 scope, failure modes and `B0_IMPLEMENTATION_AUTHORIZED=YES` from this task authorization. Do not copy the external documents into Git.

- [x] **Step 8: Verify Task 1**

  Run: `uv run pytest tests/p9b/test_hashing.py tests/contracts/test_phase9b_contracts.py -q`

  Run: `uv run python -m deepaha.contracts.export .. --version 0.8.0`

  Run: `git diff --check`

  Expected: tests pass, renderer reproduces checked-in bytes, no diff error.

### Task 2: P9-B0 Additive Identity, Parse and Member-Provenance Persistence

**Files:**
- Create: `backend/migrations/versions/20260824_0011_p9b_identity_provenance.py`
- Create: `backend/src/deepaha/p9b/models.py`
- Create: `backend/src/deepaha/p9b/identity.py`
- Create: `backend/src/deepaha/p9b/provenance.py`
- Create: `backend/src/deepaha/p9b/datasets.py`
- Create: `backend/tests/p9b/test_identity.py`
- Create: `backend/tests/p9b/test_datasets.py`
- Create: `backend/tests/integration/test_p9b_b0_persistence.py`
- Create: `backend/tests/integration/test_p9b_b0_migration.py`
- Modify: `backend/src/deepaha/documents/models.py`
- Modify: `backend/src/deepaha/documents/parser.py`
- Modify: `backend/src/deepaha/documents/html.py`
- Modify: `backend/src/deepaha/documents/pdf.py`
- Modify: `backend/src/deepaha/documents/spreadsheet.py`
- Modify: `backend/src/deepaha/documents/normalization.py`
- Modify: `backend/src/deepaha/documents/service.py`
- Modify: `backend/src/deepaha/db/models.py`
- Modify: `backend/tests/integration/test_document_service.py`

**Interfaces:**
- Consumes: B0 v0.8 contracts and canonical hashing functions.
- Produces: immutable `OpportunityUnitVersion`, single `OpportunityUnit.current_version_id`, alias/lineage services with CAS, immutable `SourceBundleRevision`/members/edges, parse-contract-aware Document/ParseAttempt identity, and manifest freeze validation.

- [x] **Step 1: Write RED DocumentParseIdentity tests**

  Prove legacy rows map to the single frozen value `phase2-locator-contract-v0.2.0`, same parser+contract is idempotent, contract change creates a new Document/ParseAttempt/derived object key, and existing `document_id` remains unchanged.

- [x] **Step 2: Write RED Unit behavior and PostgreSQL constraint tests**

  Cover natural Singleton idempotency, version uniqueness/immutability/ownership, one current pointer, CAS conflict, alias effective-window overlap, re-key collision, official-code reuse fail-closed, Singleton→Multi SPLIT, evidence-supported reversal back to the original Singleton identity, and non-reversal Multi→Singleton creating a new Unit.

- [x] **Step 3: Write RED bundle/member provenance tests**

  Persist at least two attachments whose members independently bind Source, Endpoint, CaptureObservation, VALID AcquisitionEvaluation, AcquisitionRun/Recipe, policy/fetcher/validator versions, RawArtifact hash/size/object reference, Document/parse identity, role/relation/precedence and member provenance hash. Reject non-VALID evaluation, cross-run lineage, cross-revision edge, duplicate revision number and freeze when canonical hash cannot be recomputed.

- [x] **Step 4: Write RED dataset validator tests**

  Use hand-built manifests to reject any entry-count mismatch, cross-partition atomic group, SourceBundle/revision/near-duplicate/Unit-lineage leakage, contamination of Locked by any earlier identity/lineage, answer-access mismatch, invalid cutoff and bad successor/hash.

- [x] **Step 5: Run all B0 RED tests**

  Run: `uv run pytest tests/p9b tests/integration/test_p9b_b0_persistence.py tests/integration/test_p9b_b0_migration.py tests/integration/test_document_service.py -q`

  Expected: FAIL only for missing B0 implementation/schema behavior.

- [x] **Step 6: Implement migration, ORM and services minimally**

  Add columns/tables/constraints/triggers without modifying historical migrations. Historical provenance is not synthesized; only exact existing Document IDs are preserved while parse contract gets the frozen legacy value. Unit and member history reject update/delete; current-pointer updates use explicit expected version CAS.

- [x] **Step 7: Run GREEN unit and PostgreSQL tests**

  Run the command from Step 5 with the isolated P9-B Compose environment and confirm zero failures.

- [x] **Step 8: Verify Phase 3–8 read-path invariance**

  Run focused Phase 3 identity/version, Phase 4 eligibility/rule, Phase 5 public catalog, Phase 6 personal, Phase 7 feedback and Phase 8 notification tests. Assert no production query imports or reads `UnitRuleSet` or Unit tables.

### Task 3: Close and Commit the P9-B0 Gate

**Files:**
- Create: `infra/compose.p9b.yaml`
- Create: `scripts/verify-p9b-b0.ps1`
- Create: `backend/tests/test_p9b_b0_verifier_scope.py`
- Create: `docs/gates/p9-b/b0-test-summary.md`
- Create: `docs/gates/p9-b/b0-code-review.md`
- Modify: `docs/gates/p9-b/P9B_IMPLEMENTATION_LEDGER.md`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: reproducible B0 verifier and the only B0 commit.

- [x] **Step 1: Write RED verifier-scope tests**

  Require exact isolated compose project/ports, B0 contract/hash/unit/bundle/parse/dataset suites, migration upgrade/downgrade/refusal/re-upgrade/drift, Phase 3–8 regression, P9-A verifier, secret/bypass scans, `git diff --check`, and exact B0 status output.

- [x] **Step 2: Run RED scope test, then implement verifier**

  Run: `uv run pytest tests/test_p9b_b0_verifier_scope.py -q`; expect missing verifier failure, implement minimal PowerShell verifier, then rerun to GREEN.

- [x] **Step 3: Run the complete B0 verifier**

  Run: `powershell -ExecutionPolicy Bypass -File scripts/verify-p9b-b0.ps1 -ComposeProjectName deepaha-p9b-b0-$PID`

  Expected: exit `0`, B0 tests and regression pass, migrations have no drift, P9-A statuses unchanged.

- [x] **Step 4: Perform code review**

  Review `planning-commit..working-tree` against Tasks 1–3 in passes: contracts/hashes, migration/constraints, services/concurrency, tests/verifier, backward compatibility/security. Record Critical/Important/Minor findings; fix every Critical/Important with a new RED test and rerun the complete verifier.

- [x] **Step 5: Commit B0 only after fresh verification**

  Run: `git add <only B0 paths> && git commit -m "feat: close P9-B0 identity and provenance architecture"`

  Record the commit SHA and verifier output in the ledger before entering Task 4.

### Task 4: Canonical DocumentBlock and Field-Level Locators

**Files:**
- Create: `backend/migrations/versions/20260824_0012_p9b_document_blocks.py`
- Create: `backend/src/deepaha/documents/blocks.py`
- Create: `backend/src/deepaha/documents/docx.py`
- Create: `backend/tests/documents/test_blocks.py`
- Create: `backend/tests/documents/test_docx_parser.py`
- Create: `backend/tests/integration/test_p9b_document_blocks.py`
- Modify: `backend/src/deepaha/documents/html.py`
- Modify: `backend/src/deepaha/documents/pdf.py`
- Modify: `backend/src/deepaha/documents/spreadsheet.py`
- Modify: `backend/src/deepaha/documents/parser.py`
- Modify: `backend/src/deepaha/documents/service.py`
- Modify: v0.8 contracts/export/schema files additively.

**Interfaces:**
- Consumes: exact DocumentParseIdentity and canonical hash contract.
- Produces: immutable ordered `DocumentBlock` rows and HTML element/span, PDF text-span/table-cell, XLSX cell/range and DOCX paragraph/table-cell locators. OCR remains disabled without real controlled evidence.

- [x] **Step 1: Write RED parser/block tests with controlled fixtures**
- [x] **Step 2: Run RED and confirm failures name missing block/locator behavior**
- [x] **Step 3: Implement deterministic block emission and persistence**
- [x] **Step 4: Run focused unit/integration tests and Phase 2 document regression**
- [x] **Step 5: Review, update ledger and commit `feat: add canonical P9-B document blocks`**

### Task 5: Candidate → Verification → Versioned Fact → Rule Candidate Chain

**Files:**
- Create: `backend/migrations/versions/20260824_0013_p9b_fact_lifecycle.py`
- Create: `backend/src/deepaha/p9b/facts.py`
- Create: `backend/src/deepaha/p9b/rules.py`
- Create: `backend/tests/p9b/test_fact_lifecycle.py`
- Create: `backend/tests/p9b/test_rule_promotion.py`
- Create: `backend/tests/integration/test_p9b_fact_persistence.py`
- Modify: `backend/src/deepaha/p9b/models.py`
- Modify: v0.8 contracts/export/schema files additively.

**Interfaces:**
- Consumes: Bundle revision, target composite identity, DocumentBlocks and EvidenceRefs.
- Produces: immutable ExtractionRun/Candidate/VerificationDecision/VerifiedFactSet/VerifiedFact/RuleCandidate/RuleApprovalDecision/UnitRuleSet, atomic promotion and dependency invalidation.

- [x] **Step 1: Write RED lifecycle and producer-independence tests**
- [x] **Step 2: Write RED rule-boundary tests proving Unit RuleCandidate cannot enter parent RuleSet and UnitRuleSet remains dormant**
- [x] **Step 3: Run RED, implement minimal services/constraints, then run GREEN**
- [x] **Step 4: Run Phase 4–8 regression and query/import boundary scan**
- [x] **Step 5: Review, update ledger and commit `feat: add audited P9-B fact promotion chain`**

### Task 6: Gold Annotation Governance, Frozen Manifests and Executable Benchmark

**Files:**
- Create: `backend/migrations/versions/20260824_0014_p9b_gold_benchmark.py`
- Create: `backend/src/deepaha/p9b/gold.py`
- Create: `backend/src/deepaha/p9b/benchmark.py`
- Create: `backend/src/deepaha/p9b/annotation.py`
- Create: `backend/tests/p9b/test_gold_governance.py`
- Create: `backend/tests/p9b/test_benchmark.py`
- Create: `backend/tests/integration/test_p9b_gold_isolation.py`
- Create: `config/p9b/benchmark-metric-contract.v1.json`
- Create: `config/p9b/benchmark-split-contract.v1.json`

**Interfaces:**
- Consumes: exact target/bundle/parse/block identities.
- Produces: role-separated blind annotation/import/adjudication/freeze tools, production/Gold physical isolation, manifest freeze/invalidation and executable metrics with explicit numerator/denominator/support/matching/split/leakage/cutoff.

- [ ] **Step 1: Write RED authorization/blind-state tests**
- [ ] **Step 2: Write RED benchmark tests for precision, recall, silent omission, unsupported assertion, Evidence support, segmentation, precedence and abstention**
- [ ] **Step 3: Run RED, implement minimal governance/metrics, then run GREEN**
- [ ] **Step 4: Import only identity-bearing real human labels if present; otherwise record actual counts `0` and `NOT_OBSERVED` without fabricating Gold**
- [ ] **Step 5: Review, update ledger and commit `feat: add governed P9-B gold benchmark tooling`**

### Task 7: Data/Content Egress Gate and Recorded-Response-First Minimal Model Gateway

**Files:**
- Create: `backend/migrations/versions/20260824_0015_p9b_model_gateway.py`
- Create: `backend/src/deepaha/p9b/egress.py`
- Create: `backend/src/deepaha/p9b/gateway.py`
- Create: `backend/src/deepaha/p9b/provider.py`
- Create: `backend/tests/p9b/test_egress.py`
- Create: `backend/tests/p9b/test_gateway.py`
- Create: `backend/tests/integration/test_p9b_gateway_ledger.py`
- Create: `config/p9b/provider-capabilities.v1.json`
- Modify: v0.8 contracts/export/schema files additively.

**Interfaces:**
- Consumes: minimized ordered DocumentBlocks, exact task/target/evidence identities and provider policy snapshot.
- Produces: immutable per-call EgressDecision, bounded ModelTaskSpec, ModelCallLedger, recorded-response replay and one Primary adapter slot. Fallback remains bounded and disabled until benchmark evidence justifies it.

- [ ] **Step 1: Write RED fail-closed Egress tests**
- [ ] **Step 2: Write RED TaskSpec retry/timeout/concurrency/batch/fallback/circuit-breaker and ledger/replay tests**
- [ ] **Step 3: Run RED, implement egress/gateway/replay, then run GREEN without network**
- [ ] **Step 4: Run secret/log/header redaction scans and PostgreSQL FK/hash mismatch tests**
- [ ] **Step 5: If and only if the Egress Gate passes and a policy-approved minimal real Calibration payload exists, read `D:\DeepAha\文档2\LLM-API.txt` immediately before one bounded Primary call; never print/copy the secret and record only its local-secret-file reference. Otherwise record live provider `NOT_RUN`.**
- [ ] **Step 6: Review, update ledger and commit `feat: add fail-closed P9-B model gateway`**

### Task 8: Qualification Benchmark, Replay Verifier and Final Engineering Report

**Files:**
- Create: `backend/src/deepaha/p9b/qualification.py`
- Create: `backend/src/deepaha/p9b/replay.py`
- Create: `backend/tests/p9b/test_qualification.py`
- Create: `backend/tests/p9b/test_replay.py`
- Create: `backend/tests/test_p9b_verifier_scope.py`
- Create: `scripts/verify-p9b.ps1`
- Create: `docs/gates/p9-b/P9B_FINAL_ENGINEERING_REPORT.md`
- Modify: `docs/gates/p9-b/P9B_IMPLEMENTATION_LEDGER.md`

**Interfaces:**
- Consumes: all prior Slice contracts and any identity-bearing real Gold/qualification pairs actually present.
- Produces: false-negative-protecting qualification metrics, deterministic replay/provenance verifier, complete final report and one of the four authorized Verdicts.

- [ ] **Step 1: Write RED qualification tests**

  Prove `UNKNOWN` maps to fact abstention/`UNCERTAIN`, `NEEDS_MORE_INFO` is only a reason code, and `INELIGIBLE` cannot be emitted without a deterministic conflicting approved rule plus official Evidence.

- [ ] **Step 2: Write RED final verifier-scope tests and implement verifier**

  The verifier must run contract/schema, all migrations/PostgreSQL, backend, Web build/regression, Phase 3–8, Phase 8 verifier, P9-A verifier, P9-B replay/benchmark and secret/provenance checks.

- [ ] **Step 3: Run deterministic qualification/benchmark only on real versioned labels**

  If no independently governed labels exist, emit actual support `0`, `NOT_OBSERVED` and do not calculate a passing rate.

- [ ] **Step 4: Run the complete final verifier fresh**

  Run: `powershell -ExecutionPolicy Bypass -File scripts/verify-p9b.ps1 -ComposeProjectName deepaha-p9b-final-$PID`

- [ ] **Step 5: Perform final requirements review**

  Re-read this plan and Architecture Closure; inspect full commit range and categorize findings. Fix all Critical/Important issues with RED tests; rerun the full verifier after any fix.

- [ ] **Step 6: Generate the final report and Verdict**

  Include baseline/final HEAD, architecture/differences, migrations/contracts, ledger, real Gold counts/partitions/human evidence, benchmark definitions/results/support, deterministic vs LLM, provider/token/cost/Egress, replay/provenance/locator, qualification, verifier output, unresolved issues and separate P9-A/P9-B status axes. Use exactly `P9B_ENGINEERING_PASS`, `P9B_CONDITIONAL_PASS`, `P9B_ENGINEERING_FAIL` or `STOPPED_BY_HARD_GATE`.

- [ ] **Step 7: Fresh verification and final local commit**

  Run report/status consistency checks, `git diff --check`, the full verifier if report-only edits do not affect code, then commit `docs: report P9-B engineering outcome`. Stop immediately afterward; do not push/merge/deploy.
