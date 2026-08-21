# Phase 3 延期决策

以下能力明确不进入 Phase 3：

- Phase 4 的规则 DSL、资格四态、专业目录、画像、匹配和排序；
- LLM/Model Gateway；Redis/Valkey/Celery；pgvector；
- Playwright、Docling、OCR 与 Phase 2 live 采集修改；
- 用户/API/UI、通知、反馈、商业化、生产云；
- Phase 2 Gate 合并、Phase 3 Gate 关闭、v0.3 STABLE 或发布。

受控堆叠式开发只允许在独立分支提前形成候选实现，不改变 Gate 顺序。Phase 2 关闭后仍必须
执行：更新到精确 closing commit → 基础契约差异审查 → 空库/已有数据迁移验证 → 全量本地与
独立 Phase 3 verifier → 精确 SHA 远程 CI → Gate 证据刷新。任何基础契约变化都要求修改
Phase 3 并重跑全部验证；不得降低阈值或沿用旧 SHA 证据。
