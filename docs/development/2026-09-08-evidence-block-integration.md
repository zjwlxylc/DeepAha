# 通用证据持久化接线：开发记录

状态：IN_PROGRESS，分支 `codex/evidence-block-integration`，起点是 PR #11 合并后的主线 `46a2647`。本批尚未合并或完成通用 DocumentBlock/EvidenceRef 接线。

## 先行依赖：原件准备

从既有开发提交 `17ee5d3` 移入按冻结材料准备 Document/DocumentBlock 的能力，不触发调查、来源采集、事实晋升或发布。保留源策略、原件 Hash、材料版本、运营权限检查，以及共享原件排序锁、逐原件解析提交和中断后复用已有解析版本。

适配当前主线的请求身份约定：准备表单在首次提交前取得身份，失败后保留，同样内容重试复用请求键。新增多个表单后，浏览器重试测试按实际 form 定位身份，避免误选其他操作的输入。

实际验证：

- 调查/API 定向测试 249 passed；完整 Linux mypy 407 文件无错误；Ruff 检查与 438 文件格式检查通过。
- 独立 PostgreSQL 18 容器中的原件准备/薄链路集成 14 passed，涵盖混合格式、未支持/失败材料、授权、错版本、原件变化、中断恢复、复用和并发。
- Web 定向 43 passed，TypeScript、ESLint、生产构建通过。
- 桌面与 390px 手机浏览器共 8 passed，覆盖准备/审核/登记及回执丢失重试。检查两端文档准备截图，未见横向溢出或新增控件遮挡；截图使用合成材料，不是实际人工审核证据。

数据库仅使用本批独立测试容器 `deepaha-evidence-blocks-db`，未操作用户已有数据库。浏览器端使用合成 API；真实持久化由上述 PostgreSQL 测试证明。

## 接下来

1. 移入 `47a45a9` 的 WMA 来源及版本绑定，保留其 `0037` 迁移身份并修复当前接口兼容，不带入其后的个人/规则/反馈迁移。
2. 为公共 Reader 增加通用文本片段与可重放锚点的持久化表示；历史 0.1/0.2/0.8 契约和原记录保持可读。
3. 收敛 Delivery 与正式绑定的核验接线，再追加新结果和审核展示。四条表头与内联发布时间的 Reader 映射不提前冒充持久 EvidenceRef。

始终不调用 WMA，不修改 V3 Prompt、Candidate Facts、原始 quote/locator 或六份冻结原件。当前真实结果仍为 94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED。
