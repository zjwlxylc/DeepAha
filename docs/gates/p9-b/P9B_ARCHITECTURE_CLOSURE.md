# P9-B0 Identity & Provenance Architecture Closure

Decision date: 2026-08-24 (Asia/Shanghai)

Decision status: `ACCEPTED / IMPLEMENTATION AUTHORIZED`

Implementation Gate: `B0_ENGINEERING_CLOSED`

`B0_IMPLEMENTATION_AUTHORIZED=YES`

This is the only version-controlled P9-B Architecture Closure for this implementation. It records
how the approved external design inputs map onto the repository's real Phase 3–8 and P9-A facts.
It does not copy the external design documents into Git. The bounded B0 code, migration, test and
review evidence now exists; Gold, benchmark and Release Qualification evidence does not.

## 1. Baseline and Precedence

- Required implementation baseline: `f27f096db1d7028305d4e5989360fde68b578678`.
- Direct parent and P9-A accepted candidate: `94741c19a3a8471866930a46f7e70d85b7e79a68`.
- P9-A final state remains:
  - Independent Revalidation `PASS`;
  - `P0=0 / P1=0 / P2=0`;
  - Engineering Gate `CLOSED`;
  - Release Qualification `NOT_STARTED`;
  - 100-source/14-day `NOT_RUN`;
  - Contract `IMPLEMENTED`, not `STABLE`.
- Real code, closed Engineering Gates, checked JSON Schemas and historical migrations take
  precedence over examples in design inputs.
- This task starts from the prior bounded review result
  `P0=0 / Current-B0 P1=4 / P2=1`; it closes the approved findings through Contract,
  additive migration, TDD and verification rather than reopening an unbounded P9-B audit.

## 2. External Read-only Inputs

| Document | Version | External path | SHA-256 |
| --- | --- | --- | --- |
| DeepAha Real Opportunity Gold Corpus & Document Understanding Benchmark | v1.2 | `D:/DeepAha/文档/DeepAha_Real_Opportunity_Gold_Corpus_Document_Understanding_Benchmark_v1.2.md` | `8D4ECE8B2638768358D43F37F70762B6E5F85E1360F5F7E9DE19C67FDFBDB6CC` |
| Opportunity vs OpportunityUnit Identity ADR | v1.1 | `D:/DeepAha/文档/Opportunity_vs_OpportunityUnit_Identity_ADR_v1.1.md` | `CB9FECEDF5AA8AB2C0199C11266E20F4343C492135543E4361E5FB4099E64552` |

The external files remain unmodified local inputs. Editing them would not constitute a repository
decision or a committed implementation.

## 3. Frozen Repository Corrections to the Design Examples

| Topic | External example/problem | Frozen repository decision |
| --- | --- | --- |
| OpportunityVersion identity | Several examples use an immutable UUID field named `opportunity_version_id`. | That field does not exist. Every new FK, Gold target and manifest uses `opportunity_id + opportunity_version:int`, matching the composite primary key in `opportunity_versions`. |
| Unit version identity | ADR uses a UUID UnitVersion identity. | `opportunity_unit_version_id` remains an immutable UUIDv7, while every UnitVersion also binds the real parent composite OpportunityVersion identity. |
| Locked entry count | v1.2 prose permits atomic grouping to create a small count overage. | Entry counts are exact: 30 Calibration, 70 Development, 30 Validation and 200 Locked Acceptance. `atomic_group_count` is reported separately and never substitutes for entry count. |
| Bundle member provenance | The compact design object only shows Document/Artifact-level fields. | Every immutable member owns the full acquisition and parse tuple in Section 5; no bundle-level singleton tuple can stand for multiple attachments. |
| Document versioning | Earlier concepts mention a mutable DocumentVersion. | No mutable DocumentVersion is introduced. Document and ParseAttempt identities gain additive `parse_contract_version` and an immutable parse key. |
| Unit rules | Unit facts could otherwise flow into the parent RuleSet. | Unit rules are stored only in an additive dormant UnitRuleSet after independent approval. Phase 4–8 production reads remain Opportunity-only. |

## 4. OpportunityUnit Identity and Evolution

### 4.1 Additive parent binding

`Opportunity` retains its current ID, public ID, type enum, lifecycle and Phase 3–8 read semantics.
An OpportunityUnit belongs to exactly one parent Opportunity and binds the parent version as:

```text
opportunity_id UUID
opportunity_version INTEGER
```

No existing Opportunity is silently split or reclassified when the Unit layer is introduced.

### 4.2 Current version ownership

- `OpportunityUnit.current_version_id` is the only current pointer.
- `OpportunityUnitVersion` is immutable.
- `(opportunity_unit_id, version)` is unique.
- A composite FK proves that `current_version_id` belongs to the same Unit.
- Each UnitVersion binds `(opportunity_id, opportunity_version)` to an existing
  OpportunityVersion.
- Advancing the current pointer uses compare-and-swap with an explicit expected current version;
  a mismatch returns `CONCURRENT_VERSION_CONFLICT` and creates no second current state.

### 4.3 Keys, aliases and fail-closed resolution

- The current natural key namespace is `(opportunity_id, normalized_current_unit_key)` for a
  non-retired Unit.
- `__default_singleton__` is the only default Singleton key.
- Re-key retains the stable Unit ID, creates a new UnitVersion, closes the old current-alias
  effective window and opens the new one with official Evidence and exact bundle revision.
- Alias windows for the same normalized key cannot overlap across distinct Units in the same
  Opportunity.
- A collision, reused official code with changed canonical meaning, or an uncertain re-key returns
  `IDENTITY_COLLISION` and requires an accountable external decision. No automatic merge occurs.

### 4.4 Singleton, split, merge and reversal

- Singleton→Multi keeps the Singleton ID and history, ends the current Singleton version with
  `SUPERSEDED_BY_SEGMENTATION`, creates new child Unit identities/versions and a `SPLIT` lineage
  event with exact source and target versions.
- Multi→Singleton may reuse the original Singleton identity only when an explicit, Evidence-bound
  `REVERSAL` reverses that Singleton's prior split. Reuse always creates a new Singleton version;
  no historical version is reactivated or mutated.
- Every other Multi→Singleton transition is a `MERGE` that creates a new Unit identity.
- Lineage events and members are immutable. Reversal adds a new event and new versions; it never
  deletes or rewrites history.

## 5. SourceBundle Revision and Member-level Provenance

`SourceBundle` is the stable aggregate for one Opportunity. A revision is an immutable evidence
graph snapshot with unique `(source_bundle_id, revision_number)`, explicit relation and precedence
graph versions, effective time, status and canonical hash.

Every `SourceBundleMember` independently binds all of the following:

```text
source_id
endpoint_id
capture_observation_id
acquisition_evaluation_id + validation_status=VALID
acquisition_run_id
recipe_id + recipe_version
endpoint policy version
fetch strategy
fetcher name + version
validator name + version
raw_artifact_id + content_sha256 + byte_size + storage bucket + object key
document_id
document_parse_key
parser name + version + parse_contract_version
member role
relation type + related member within the same revision
precedence
effective window
member_provenance_hash
```

Composite foreign keys must prove Source/Endpoint/Observation/Evaluation/Run/Artifact/Document
lineage. `VALID` is part of the referenced evaluation tuple, so a challenge or other non-VALID
evaluation cannot freeze by application convention alone. A relation edge cannot cross revisions.

A revision freezes only when:

1. every member has a complete current P9-A tuple;
2. every acquisition evaluation is exactly `VALID`;
3. artifact ID/hash/size/object reference recomputes and matches;
4. Document parse identity recomputes and matches the same Artifact;
5. all relationship endpoints belong to that revision;
6. every member provenance hash recomputes;
7. the revision canonical bundle hash recomputes from the ordered member and edge projection.

Historical Documents without complete P9-A provenance are not backfilled with invented values and
cannot enter Interim or Locked Gold.

## 6. DocumentParseIdentity

The frozen legacy parse-contract value is:

```text
phase2-locator-contract-v0.2.0
```

The parse key is:

```text
hash(
  artifact_id
  + artifact_sha256
  + parser_name
  + parser_version
  + parse_contract_version
)
```

The additive migration preserves every existing `document_id`, assigns only the single truthful
legacy contract value to historical Document/ParseAttempt rows, and calculates their parse key.
Document, ParseAttempt uniqueness/idempotency queries and derived text object keys include
`parse_contract_version`. A parser or contract change produces a new immutable Document and
ParseAttempt; it never mutates the previous Document.

## 7. Dataset Partition Foundation

The four manifest entry targets are exact:

| Partition | Exact entry count | Answer access |
| --- | ---: | --- |
| `CALIBRATION` | 30 | `ASSISTED_CALIBRATION` |
| `DEVELOPMENT` | 70 | `DEVELOPMENT_VISIBLE` |
| `VALIDATION` | 30 | `VALIDATION_BLIND` until the tuning-cycle reveal |
| `LOCKED_ACCEPTANCE` | 200 | `LOCKED_BLIND` until the blind run completes |

Each manifest records expected and actual entry count, distinct atomic group count, exact target
composite identities, SourceBundle/revision/hash, near-duplicate groups, Unit lineage groups,
evaluation cutoff, answer access, freeze actor/time, invalidation reason, successor and manifest
hash.

The same SourceBundle lineage, revision/correction chain, attachment family, near-duplicate family,
OpportunityUnit lineage or connected atomic leakage group cannot cross partitions. Once any target
identity or connected lineage appears in Calibration, Development or Validation, it is permanently
ineligible for Locked Acceptance. A replacement for an invalidated Locked entry must come from a
new unseen atomic group; changing a version number does not cleanse answer exposure.

## 8. Canonical Hash Contract

- Algorithm: SHA-256.
- Hash contract version: `p9b-canonical-json-sha256-v1`.
- Serialization: UTF-8 JSON, lexicographic object-key order, no insignificant whitespace,
  array order preserved, JSON `null` retained, Unicode unescaped, NaN/Infinity rejected.
- Typed values such as UUID and datetime must be normalized explicitly before serialization;
  implicit string conversion is forbidden.
- Domain separator:

```text
deepaha:p9b:<domain>:p9b-canonical-json-sha256-v1\0
```

- Frozen domains: `document_parse_key`, `canonical_bundle_hash`, `split_manifest_hash`,
  `member_provenance_hash`.
- Checked golden vectors cover field order, null, Unicode, array order and domain separation.

### 8.1 Additive DocumentBlock hash domains

The DocumentBlock Slice adds `document_block_hash` and `evidence_binding_hash` without changing the
B0 enum or any B0 golden vector. Both use the same frozen algorithm, serialization, null handling,
domain separator and hash-contract version. Their checked golden vectors bind ordered block content,
the exact Document parse key, structural locator and immutable block ID.

Historical P9-A replay continues to select the `0.2.0` parser/version/contract. P9-B block-capable
parsers are explicit parallel implementations with version `0.8.0` and parse contract
`p9b-document-block-contract-v0.8.0`; selecting one creates a new immutable Document identity.
Legacy parse identities cannot persist DocumentBlock rows.

### 8.2 Fact promotion and dormant Unit rule persistence

Migration `20260824_0013` adds an audited production write chain without changing a Phase 4–8
reader:

```text
ExtractionRun + ordered ExtractionRunInputBlock
  -> ExtractionCandidate + exact block/EvidenceRef bindings
  -> immutable FactVerificationDecision
  -> VersionedVerifiedFactSet + immutable VerifiedFact + dependency fingerprints
  -> RuleCandidate + immutable RuleApprovalDecision
  -> dormant UnitRuleSet (UNIT only)
```

- Every target retains `opportunity_id + opportunity_version:int`. A `UNIT` target additionally
  requires the exact `opportunity_unit_id + opportunity_unit_version_id`; an Opportunity target
  forbids those fields.
- An ExtractionRun accepts only blocks whose Documents are members of its exact frozen
  SourceBundleRevision. The ordered block set and Evidence bindings are hash-bound and persisted as
  relational rows.
- Candidate producers cannot act as their verifier, and a producer response cannot be reused as a
  verification response. A known fact requires `APPROVE + SUPPORTED + PASSED`; an explicit
  abstention becomes fact state `UNKNOWN`, never a fifth eligibility status.
- VerifiedFact content and Evidence links are insert-only. A FactSet may leave `ACTIVE` only through
  an immutable transition record; supersession is atomic and dependency invalidation records both
  expected and observed fingerprints.
- RuleCandidate Evidence must be reachable from its selected VerifiedFacts. Approval is a separate
  immutable record whose approver identity differs from the candidate producer.
- `UnitRuleSet.activation_status` is database-constrained to `DORMANT`. No legacy RuleSet,
  Eligibility, Public Catalog, Personal Action, Ranking, Notification or Feedback reader imports
  the new Unit tables.

All Slice fixtures are synthetic engineering inputs. They are not Gold, independent human evidence
or Release Qualification evidence.

## 9. Stage 1 Read-path and Trust Boundaries

- Document remains distinct from Opportunity and OpportunityUnit.
- Gold tables and production fact tables remain physically and logically separate.
- Parser/model outputs are Candidates until an independent VerificationDecision approves them.
- Candidate producers cannot approve their own output or Evidence support.
- Unit RuleCandidate cannot compile into a parent Opportunity RuleSet.
- UnitRuleSet is dormant and is not imported or queried by existing Eligibility, Public Catalog,
  Personal Action, Ranking, Notification or Feedback services.
- Production eligibility remains exactly four-state. `UNKNOWN` is an extraction/fact abstention;
  `NEEDS_MORE_INFO` is only an `UNCERTAIN` reason code.
- No model can produce final `INELIGIBLE`; that state still requires a deterministic conflicting
  approved rule and official Evidence.

## 10. B0 Gate and Failure Modes

B0 closes only after all of the following pass on the exact candidate:

1. v0.8 Pydantic and checked JSON Schema compatibility tests;
2. canonical hash golden vectors;
3. additive migration upgrade, empty downgrade, populated-history refusal, re-upgrade and drift;
4. PostgreSQL constraints for Unit ownership/version/current pointer/alias windows/lineage and
   SourceBundle member provenance/revision freeze;
5. deterministic CAS and transition tests;
6. exact split/leakage/answer-access validator tests;
7. Phase 3–8 regression and unchanged legacy read-path checks;
8. P9-A verifier with its status axes unchanged;
9. independent diff review with no Critical or Important finding;
10. a dedicated local B0 commit.

Fail closed with no B0 commit or next Slice when a destructive migration, changed Phase 3–8 core
semantics, unverifiable provenance, wrong parent identity, cross-revision relation, Unit collision,
hash-contract mismatch or repeated formal Gate failure is observed.

The dedicated evidence in `P9B_B0_TEST_SUMMARY.md` and `P9B_B0_CODE_REVIEW.md` closes the bounded
B0 Engineering Gate. It does not close the overall P9-B Engineering Gate, start Release
Qualification, create Gold, approve external egress or mark v0.8 `STABLE`.
