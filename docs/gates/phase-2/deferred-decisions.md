# Phase 2 延期决策

以下能力明确未进入 Phase 2：

- Phase 3 的 Document → Opportunity Resolver、Opportunity Version/Event、更正/延期归并、
  稳定 ID 合并/拆分；
- 规则、资格四态、画像、排序、Golden Dataset 业务准确率；
- LLM/Model Gateway、Docling、OCR、默认 Playwright；
- Redis/Valkey/Celery、pgvector、异步编排、生产云；
- 用户/API/UI、通知、反馈、商业化与生产采集调度。

动态页面、扫描 PDF 或解析长尾只有在固定失败样本和新 spec 存在时才重新评审。上述能力均不
进入 Phase 2 分支。用户已另行授权 Phase 3 在独立任务/worktree/branch 实施，但 Phase 2 Gate
关闭前不得合并、发布或宣称 Phase 3 已验证完成；也不得用降低 live 阈值或通用来源特例消除
真实失败。
