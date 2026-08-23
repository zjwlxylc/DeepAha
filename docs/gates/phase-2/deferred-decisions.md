# Phase 2 延期决策

以下能力明确未进入 Phase 2：

- Phase 3 的 Document → Opportunity Resolver、Opportunity Version/Event、更正/延期归并、
  稳定 ID 合并/拆分；
- 规则、资格四态、画像、排序、Golden Dataset 业务准确率；
- LLM/Model Gateway、Docling、OCR、默认 Playwright；
- Redis/Valkey/Celery、pgvector、异步编排、生产云；
- 用户/API/UI、通知、反馈、商业化与生产采集调度。

动态页面、扫描 PDF 或解析长尾只有在固定失败样本和新 spec 存在时才重新评审。上述能力均不
进入 Phase 2 分支。Phase 3 及后续能力在各自独立任务/worktree/branch 实施并由自己的
Engineering Gate 判定；Phase 2 Release Qualification 未取得 `QUALIFIED` 不再阻塞其正常工程开发、评审或
状态归一化。阶段间真实的契约、迁移和分支依赖仍须兼容验证，生产发布仍须满足对应 Release
Qualification；不得用降低 live 阈值或通用来源特例消除真实失败。
