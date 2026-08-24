# P9-B DocumentBlock & Field Locator Slice — Test Summary

Date: 2026-08-24 (Asia/Shanghai)

This evidence covers engineering behavior on synthetic/controlled fixtures. It does not represent
real Gold, independent human verification, production accuracy, OCR coverage or Release
Qualification.

## Formal verifier

Command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-p9b-document-blocks.ps1 `
  -ComposeProjectName deepaha-p9b-blocks-final-12872
```

Observed final result: exit `0`.

| Check | Observed result |
| --- | --- |
| Backend non-integration regression | `674 passed, 297 deselected in 21.93s` |
| Web Vitest | `24` files, `61` tests passed |
| Web production build | passed |
| DocumentBlock contract/parser/verifier tests | `23 passed` |
| DocumentBlock PostgreSQL/migration/DocumentService tests | `17 passed` |
| Full PostgreSQL integration regression | `293 passed, 4 skipped, 674 deselected in 113.55s` |
| Alembic drift before downgrade | no new upgrade operations detected |
| Empty migration downgrade/re-upgrade | `20260824_0012 -> 20260824_0011 -> 20260824_0012`, passed |
| Alembic drift after re-upgrade | no new upgrade operations detected |
| Exact compose cleanup | containers, volumes and network removed |

The first formal verifier run stopped at the root formatter check before database startup. After
applying the formatter, the full Gate was rerun successfully; the post-review final run above also
completed from the beginning with exit `0`.

## Evidence boundary

- HTML, text-PDF, XLSX and DOCX parser/locator behavior uses repository synthetic fixtures.
- PDF table-cell support is exercised with deterministic tabular text input.
- XLSX range-to-cell parent ownership is persisted in PostgreSQL.
- DOCX uses deterministic OOXML parsing with macro, external relationship and path traversal gates.
- Real controlled DOCX/XLSX Gold entries: `0`.
- Independent Annotator/Verifier/Adjudicator decisions: `0 / NOT_OBSERVED`.
- OCR: `NOT_RUN / DISABLED`.
- Release Qualification: `NOT_STARTED`.

Verifier status output:

```text
P9-B DOCUMENT BLOCK SLICE ENGINEERING GATE=CLOSED
Real DOCX/XLSX Gold coverage=NOT_OBSERVED
Release Qualification=NOT_STARTED
```
