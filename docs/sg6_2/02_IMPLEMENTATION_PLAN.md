# SG6.2 Qualification Evidence Compiler Implementation Plan

**Goal:** 自动把 WMA 已读懂、且有可靠 Evidence 的资格条件编译到 SG4 计算轨，显著降低无意义 UNCERTAIN，同时绝不恢复逐字段人工审核。

**Architecture:** 新增独立 `qualification_compiler.py` 负责字段别名、语义编译、coverage/unresolved/risk；`eligibility.py` 只负责 Evidence 验证和确定性比较。Compiler 输出可重建并可缓存到 CatalogTarget metadata；不改原事实权威表。

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy/SQLite/PostgreSQL, openpyxl, zipfile/docx XML/pdf text artifacts.

**Spec:** `docs/sg6_2/01_DESIGN.md`

## Global Constraints
- 不恢复逐字段人工审核。
- 不新增 reviewer 逐条件确认接口。
- `INELIGIBLE` 必须仍为 evidence-backed deterministic conflict。
- 不调用外部 LLM/WMA 进行资格裁决。
- SG1-SG6 业务核心与 API 保持兼容。

## Review Focus
- WMA 英文字段别名必须进入同一 canonical type。
- “学位/国籍/政治面貌/经历/证书”等常见硬条件不能再全部落 UNSUPPORTED。
- PDF/DOCX/图片没有可核验派生文本时必须 fail closed。
- coverage 不能因为“识别了几个字段”就假装 COMPLETE。
- 例外/OR/放宽条款继续阻止硬否定。

### Task 1: Canonical field alias + compiler
Create `backend/src/deepaha/product/qualification_compiler.py`; test aliases and deterministic parsers.

### Task 2: Evidence resolver expansion
Extend evidence verification for DOCX and source-linked derived text/OCR artifacts; no runtime OCR.

### Task 3: Coverage/unresolved/risk
Generate service-owned coverage and unresolved reasons; integrate SG4 result.

### Task 4: Rebuild/upgrade and API projection
Add `upgrade-sg6-2` rebuild of target derived compiler metadata and expose compiler summary in fit API; no authority table mutation.

### Task 5: Real-data benchmark
Run before/after on uploaded WMA database: count zero-requirement, NONE/PARTIAL/COMPLETE, status distribution, evidence support, and verify no old tables/object hashes change.

### Task 6: Full regression / package
Run SG1-SG6.1 product tests, frontend checks, compile, document Windows reproduction, build SHA manifest and ZIP.
