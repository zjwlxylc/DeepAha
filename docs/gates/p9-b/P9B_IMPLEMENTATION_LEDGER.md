# P9-B Implementation and Commit Ledger

This ledger records observed engineering evidence. It does not turn a plan, fixture, synthetic
label, model output or missing human decision into Gold or Release Qualification evidence.

## Start Baseline — 2026-08-24 (Asia/Shanghai)

- Workspace: `C:/Users/LENOVO/.codex/worktrees/0d76/DeepAha`
- Isolation: Codex App linked worktree (`git-dir` differs from `git-common-dir`); no nested
  worktree created.
- Git state: detached `HEAD` at `f27f096db1d7028305d4e5989360fde68b578678`.
- Required baseline ancestor: exact `HEAD`; `git merge-base --is-ancestor` exit `0`.
- Direct parent: `94741c19a3a8471866930a46f7e70d85b7e79a68`.
- Pre-task status: no staged, unstaged or untracked paths.
- P9-A state retained: Independent Revalidation `PASS`; `P0=0 / P1=0 / P2=0`;
  Engineering Gate `CLOSED`; Release Qualification `NOT_STARTED`; 100-source/14-day `NOT_RUN`;
  Contract `IMPLEMENTED`, not `STABLE`.

### Read-only design inputs

| Input | External path | SHA-256 |
| --- | --- | --- |
| Gold Corpus & Document Understanding Benchmark v1.2 | `D:/DeepAha/文档/DeepAha_Real_Opportunity_Gold_Corpus_Document_Understanding_Benchmark_v1.2.md` | `8D4ECE8B2638768358D43F37F70762B6E5F85E1360F5F7E9DE19C67FDFBDB6CC` |
| Opportunity vs OpportunityUnit Identity ADR v1.1 | `D:/DeepAha/文档/Opportunity_vs_OpportunityUnit_Identity_ADR_v1.1.md` | `CB9FECEDF5AA8AB2C0199C11266E20F4343C492135543E4361E5FB4099E64552` |

The external files are read-only inputs and are not copied into Git. The repository Architecture
Closure created by B0 will record the authoritative implementation differences, including the
existing composite OpportunityVersion identity `opportunity_id + opportunity_version:int`.

### Baseline verification

Command:

```powershell
Set-Location backend
uv run pytest
```

Observed result: exit `0`; `627 passed, 274 deselected in 56.55s`.

This is the non-integration/non-live baseline only. PostgreSQL, migrations, Web, Phase 8 and P9-A
verifiers remain required at the applicable Slice gates.

## Slice Ledger

| Slice | Base | Head | Verification | Review | Commit |
| --- | --- | --- | --- | --- | --- |
| Planning | `f27f096db1d7028305d4e5989360fde68b578678` | planning worktree | placeholder scan clean; `git diff --check` exit `0` | spec coverage/type/identity self-review complete | recorded by planning commit |
| P9-B0 Identity & Provenance Architecture Closure | `a5ca543c961c2077df5688d29e888021fe655821` | `3b5da45e6a19899f4c477aa3cf32fc1445254a95` | B0 verifier exit `0`: backend `661`, deterministic `90`, B0 PostgreSQL `29`, full PostgreSQL `288`; P9-A verifier exit `0` | `B0_DIFF_REVIEW_PASS`; P0/P1/P2=`0/0/0` | `3b5da45e6a19899f4c477aa3cf32fc1445254a95` |
| DocumentBlock & Field Locators | `3b5da45e6a19899f4c477aa3cf32fc1445254a95` | dedicated DocumentBlock commit (this tree) | final verifier exit `0`: backend `674`, directed `23`, PostgreSQL directed `17`, full PostgreSQL `293`, Web `61`; downgrade/re-upgrade/drift passed | `DOCUMENT_BLOCK_DIFF_REVIEW_PASS`; P0/P1/P2=`0/0/0` | dedicated local commit |
| Fact Promotion & Dormant Unit Rules | `10a7103a5d080d1ee9d1b114b3963aaaab4b053c` | dedicated fact-chain commit (this tree) | final verifier exit `0`: backend `684`, directed `22`, PostgreSQL directed `5`, full PostgreSQL `298`, Web `61`; downgrade/re-upgrade/drift passed | `FACT_PROMOTION_DIFF_REVIEW_PASS`; P0/P1/P2=`0/0/0` | dedicated local commit |
| Gold Governance & Benchmark | pending | pending | not run | not run | not committed |
| Egress & Minimal Model Gateway | pending | pending | not run | not run | not committed |
| Qualification, Replay & Final Report | pending | pending | not run | not run | not committed |

Rows are updated only from fresh command output and Git facts. Missing external evidence remains
`NOT_RUN` or `NOT_OBSERVED`.
