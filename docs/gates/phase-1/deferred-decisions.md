# Phase 1 延期决策

以下事项明确不在 Phase 1 实现内；它们不是已实现能力，也不因本 Gate 的本地结果而自动获批。

1. **实时捕获观察记录。** Phase 1 只处理固定捕获重放；同一 `(source_id, content_sha256)` 但抓取元数据不同会返回 `RAW_ARTIFACT_PROVENANCE_CONFLICT`。进入 Phase 2 实时采集前，必须设计独立观察记录，不能静默吞掉新的抓取事实。
2. **采集与解析。** Source Registry、运行调度、限速/重试、源健康、HTML/PDF/Excel/图片解析、跨附件冲突和更细证据定位均延期到 Phase 2 的独立设计。
3. **中国首发官方样本。** 当前 OGL 样本只证明技术契约。浙江/中国样本必须另行确认公开使用与转载边界后才能加入，不得用当前英国样本替代覆盖证明。
4. **Opportunity 版本与归并。** Phase 1 只建立独立稳定身份，`current_version=null`；`OpportunityVersion`、Resolver、合并/拆分、更正和延期进入 Phase 3。
5. **生产对象存储。** Moto 5.2.2 是本地/CI S3 兼容实现，不代表生产云厂商、权限、加密、备份、保留策略或基础设施已经选择或验证。
6. **后续系统能力。** LLM/Model Gateway、规则与资格、排序、用户系统、业务页面、Redis、向量检索、异步编排和生产云基础设施继续遵守路线图阶段顺序，本阶段没有占位实现。
