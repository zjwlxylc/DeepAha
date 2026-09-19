# SG6.2 Final Verification

Release: **3.6.2-rc1 / SG6.2 Qualification Evidence Compiler**

## Final source tree

- `backend/tests/product`: **21 files / 202 collected tests**.
- Every test file executed in an isolated pytest process and obtained `RC=0`; **202/202 passed, 0 failed**.
- `test_qualification_compiler.py`: 19 passed.
- `test_sg6_2_frontend_contract.py`: 3 passed.
- `test_sg6_2_upgrade.py`: 3 passed.
- SG4 Eligibility: 17 passed.
- SG5 Value/Priority: 13 passed.

The environment has a long-standing pytest/TestClient teardown issue when many files are chained in one long command. Files that hit the outer batch timeout were rerun alone and obtained explicit `RC=0`; no product assertion failure was hidden as a timeout.

## Frontend / compile

- `check-product.mjs`: PASS
- `check-sg5.mjs`: PASS
- `check-sg5-1.mjs`: PASS
- `check-sg6.mjs`: PASS
- `check-sg6-1.mjs`: PASS
- `python -m compileall -q backend/src/deepaha/product`: PASS
- active package version: `3.6.2-rc1`

## Real WMA data replay

User-provided database/object-store snapshot was copied; original upload was not modified.

SG6.1 baseline → SG6.2 final on 328 current targets:

- targets with zero recognized qualification requirements: **189 → 0**;
- complete test profile: **300 UNCERTAIN / 28 INELIGIBLE → 185 UNCERTAIN / 139 INELIGIBLE / 4 LIKELY_ELIGIBLE**;
- actual-like profile (`专科 + 计算机 + 宁波`): **97 INELIGIBLE / 231 UNCERTAIN → 199 INELIGIBLE / 129 UNCERTAIN**;
- evidence LOCATED: **966 → 1543**;
- SG6.1 unsafe headline featured count for the actual-like profile: **3 → 0**.

300 public-institution/recruitment targets for that actual-like profile:

- 199 formal `INELIGIBLE`;
- 100 `UNCERTAIN + HIGH qualification risk` (primarily image-only PDFs without a verifiable hash-bound OCR derivative);
- 1 ordinary `UNCERTAIN`.

## Backup-first derived upgrade

Fresh real-data copy:

- first `upgrade-sg6-2`: backup verified; 328 targets refreshed;
- second run: `already_current=true`, 0 refreshed, `data_modified=false`;
- Opportunity / Identity / Unit / Decision / Publication / Revision / Snapshot / Task / Account / Profile table digests unchanged;
- object store: **252 files**, aggregate SHA-256 unchanged:
  `3a6a65a223ce371d80976fddcb6efcc3ea80f4b063fb4cd4780efe307778ff54`.

## Old-route regression gate

- reviewer still has only one whole-result decision endpoint: `/api/review/{id}/decision`;
- retired legacy `/api/v1/review/*` writes still return 410;
- SG6.2 adds no field-approve API, no per-position field review UI, no VerifiedFact/Rule manual promotion action;
- `upgrade-sg6-2` writes only rebuildable CatalogTarget compiler metadata + compiler Meta version;
- WMA calls during SG6.2 upgrade/benchmark: **0**.

## Acceptance boundary

The release does **not** claim that all opportunities are decidable. Semantic major matching, OR/exception clauses, application quotas, ambiguous age rules, and evidence that cannot be independently located continue to fail closed as `UNCERTAIN`. Windows browser/user acceptance remains pending.
