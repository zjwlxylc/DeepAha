# 通用核验接线与不可变调查回执

实现状态：IMPLEMENTED；候选集成尚在验证。接续架构审查的 C/D 批次，基线为 PR #12 合并 `7d34ed7`。本次不部署、不批准事实，也不把工程通过写成发布资格通过。

## 结果与边界

Delivery 的活动路径改为共同 EvidenceVerifier，继续保留两份冻结 Schema、实际文件字节、跨文件实体/字段一致性与资源上限。旧格式函数移到 `delivery_legacy.py`，显式 `validate_legacy_delivery` 仅用于旧结果离线回放；没有请求参数可切回旧裁决。独立评审确认五个迁移函数的 AST 与合并前一致。

文档准备改用同一注册表的 ReaderDocumentParser，生成独立的解析身份。旧 0.1/0.2/0.8 文档及历史来源归属不改写；DOCX 的既有文档读取仍保留，但没有共同 Reader 时不产生字段证据 PASS。二进制 DOC 没有新解析器。

新增 `investigation_evidence_checks` 与迁移 `20260908_0039`。文档准备后追加机械回执，含输入/结果 Hash、原始引文和定位、Reader/比较版本、表示 Hash、来源字符范围、实际 Document/ParseAttempt/DocumentBlock/EvidenceRef 与 verdict。相同输入重复准备复用原回执；新版本追加历史；不会修改 task.delivery、Candidate Facts 或人工决定。没有持久绑定时，即使字面层 PASS，新回执仍为 UNVERIFIED。

数据库约束不仅检查 Hash，还逐条核对冻结引用次序、实体/字段、原引文/locator、材料集合、实际持久引用和解析身份、计数及总体结论。UPDATE/DELETE 被拒绝；存在回执历史时拒绝 downgrade，避免删除审计记录。旧 WMA 迁移保护的测试改为直接运行原 0037 guard，保证它本身仍经过验证，而非只断言较新的回执保护提前拒绝。

审核页面分别显示内容、定位、持久绑定，保留原定位、Reader、候选字符位置及历史回执。只有旧布尔值时明确显示旧版结果，不虚构新核验维度。保持桌面操作优先、手机可读。

## 已运行验证

- 同一六份真实输入，经旧 Delivery 入库、当前文档准备、新回执和只读展示：**124 条逐条一致；94 PASS / 0 FAIL / 30 UNVERIFIED；Delivery UNVERIFIED**。
- 四条折行表头及一条内联发布时间均关联实际 EvidenceRef。旧回执、事实、引文、locator 和原件 Hash 不变。临时数据库/对象目录清理完成；WMA/官网调用、业务库写入和人工审批均为零。
- 后端完整非集成：1292 passed；共同核验与 Delivery 定向：204 passed；数据库相关：52 passed。
- Ruff 全部通过；mypy Linux/Windows：420 文件通过。
- Web：139 passed、lint/typecheck/生产构建通过；桌面/手机浏览器 10 passed，覆盖丢失回执重试、准备、内容与定位展示、下载和内部材料审核。详情展开后另做两端视觉检查。
- 独立评审指出一项回执关系约束问题，已用 PostgreSQL 失败测试复现并修复；修复测试覆盖缺失引用、错误计数、改写引文、错误索引、错误引用 ID、错误材料集合和不可变性。其余常规复核未发现明确回归；独立 7 项 Delivery 测试与 3 类实际 UI 状态检查通过。

完整 PostgreSQL/Moto 数据库矩阵：516 passed / 3 skipped，跳过项依赖专用数据库名称，由对应 CI 作业执行。其后补充检查器版本进入 input_hash，19 项定向数据库、204 项公共/Delivery 回归及同一真实案例重放再次通过；Alembic check 无模型差异。候选 CI 尚待执行。

## 可复现证据

- `docs/development/evidence/2026-09-08-investigation-receipt-replay.py`
- `docs/development/evidence/2026-09-08-investigation-receipt-replay.json`
- `docs/development/evidence/2026-09-08-receipt-integration-tests.txt`
- `backend/tests/integration/test_investigation_evidence_checks.py`
- `web/e2e/investigations.spec.ts`

30 条 Word 的已保存诊断读取不自动晋升为共同 Reader 或可执行定位。后续若开发 DOC/扫描件适配器，需单独建立确定性读取、范围与可靠性证据；当前不修改 Prompt、不重跑 WMA，不以降低 Evidence Gate 换取通过。
