# 通用证据持久化接线：开发记录

状态：通用持久化及只读绑定已 IMPLEMENTED，本地回归与失败项修复复核完成，候选 CI 待运行，尚未合并。分支 `codex/evidence-block-integration`，起点是 PR #11 合并后的主线 `46a2647`。调查回执与审核页面的共同结果接线（批次 C）尚未实施；不把这一批当成全部架构迁移完成。

## 先行依赖：原件准备

从既有开发提交 `17ee5d3` 移入按冻结材料准备 Document/DocumentBlock 的能力，不触发调查、来源采集、事实晋升或发布。保留源策略、原件 Hash、材料版本、运营权限检查，以及共享原件排序锁、逐原件解析提交和中断后复用已有解析版本。

适配当前主线的请求身份约定：准备表单在首次提交前取得身份，失败后保留，同样内容重试复用请求键。新增多个表单后，浏览器重试测试按实际 form 定位身份，避免误选其他操作的输入。

实际验证：

- 调查/API 定向测试 249 passed；完整 Linux mypy 407 文件无错误；Ruff 检查与 438 文件格式检查通过。
- 独立 PostgreSQL 18 容器中的原件准备/薄链路集成 14 passed，涵盖混合格式、未支持/失败材料、授权、错版本、原件变化、中断恢复、复用和并发。
- Web 定向 43 passed，TypeScript、ESLint、生产构建通过。
- 桌面与 390px 手机浏览器共 8 passed，覆盖准备/审核/登记及回执丢失重试。检查两端文档准备截图，未见横向溢出或新增控件遮挡；截图使用合成材料，不是实际人工审核证据。

数据库仅使用本批独立测试容器 `deepaha-evidence-blocks-db`，未操作用户已有数据库。浏览器端使用合成 API；真实持久化由上述 PostgreSQL 测试证明。

## 来源绑定依赖

已移入 `47a45a9` 的 WMA 来源及版本绑定，保留 `20260907_0037` 迁移。绑定明确记录 Direct WMA，而不伪造 Acquisition/CaptureObservation。未映射的岗位保持未映射，不创建正式事实。服务器重新核对当前审核身份、材料 Hash、机会/岗位版本及上一份归属修订；来源包与归属回执保留历史。

修复 52 项新测试的类型错误，并适配主线的稳定表单请求身份；丢失回执后保留机会、岗位、理由，重试只写一次。当前 Linux/Windows 完整 mypy 均 416 文件无错误；Web 定向 48 项、构建及桌面/手机 10 个浏览器场景通过。独立只读评审未发现遗留 P2+；旧 ACQUISITION 有/无 EvidenceRef 两类成员 Hash 负载与主线保持一致。

## 一次性通用锚点扩展

新增 `READER_TEXT_SPAN` 和 `reader_anchor`。`contracts/schemas/v0.9.0/reader-anchor.schema.json` 只描述新的通用锚点，不取代 0.1/0.2/0.8。Anchor 固定记录 Reader 四维身份、原件/表示/投影 Hash、投影 ID 与字符范围；它不是原文件字节偏移。原始文字位置由相同 Reader 从原件重放，表示 Hash 同时固定投影到原始 text-node/page/cell 字符位置的映射。

`ReaderDocumentParser` 复用 DocumentService；新 Reader 身份产生独立 parse key。可读派生文档继续采用既有 NFC 规范，证据块保留 Reader 的字面文本，不能用可读文档的规范化去改写引文。`PreparedDocumentEvidence` 一次检查原件、解析尝试、全量块集合、EvidenceRef、派生对象字节及所有 Hash，再让共同 Verifier 使用同一缓存核验引用；只有 PASS 才返回真实 block_id/evidence_ref_id。该操作只读，不批准事实。

新增迁移 `20260908_0038` 依赖当前唯一 head `20260907_0037`，不修改历史迁移或引入长分支的其余迁移。新块与引用必须通过严格外壳、Hash、外键与不可变约束。存在 0.9 历史时拒绝回退；空库可以回退再升级。未来格式由注册 Reader 解析/回放，不再扩充本次通用块种类。

评审发现并修复两项 P2：

- 原先未进入来源包的 EvidenceRef 仍可能被原地改写：真实 PostgreSQL 失败测试复现后，增加 0.9 引用的独立 UPDATE/DELETE 拒绝，包括通过修改版本绕过保护。
- 超长 DOM 路径超出持久锚点上限：原先泄漏 ValidationError，现在记录稳定的 `READER_ANCHOR_INVALID` 解析失败，不产生部分 Document。

独立复核关闭两项问题，并检查共同持久回放未发现遗留 P2+。定向 PostgreSQL 49 项通过；公共核验 107 项通过；后端非集成回归 1,290 项通过（其后新增的 Schema 导出一致性测试已包含在 107 项中）。完整 PostgreSQL/Moto 首轮矩阵为 498 passed / 5 failed / 3 skipped，5 个失败均为旧迁移测试夹具未补当前 ORM 的 WMA 列；补齐测试专用兼容列后，相关 6 项旧迁移及 12 项新 Reader 持久化测试全部通过（18 passed），没有修改历史迁移或迁移验收断言。3 个跳过为特定数据库名称场景，将由对应 CI 作业运行。Web 全量 137 项通过，Alembic 模型一致性检查通过。

新增合成格式只实现并注册测试 Adapter，就能使用相同数据库种类、DocumentService 和正式回放链持久绑定；反复核验不再次读取原件。超长定位也已通过真实 PostgreSQL 测试证明会记录 FAILED ParseAttempt。两项新增测试使用独立临时库，测试后已清理。

## 冻结样本的实际持久回放

使用同一六份冻结文件，在独立临时 PostgreSQL 数据库与 LocalFileObjectStore 中导入、解析并绑定；没有调用 WMA，没有修改业务数据库、Candidate Facts、原始 quote 或 locator。

结果为 **94 PASS / 0 FAIL / 30 UNVERIFIED；Delivery UNVERIFIED**。94 条均具备实际持久 EvidenceRef，包括四条折行表头和一条内联发布时间。30 条旧 Word 仍无生产 Reader，未借已有诊断读回升级为 PASS。六份原件 Hash 前后一致；临时数据库与对象目录已移除。

- 脚本：`docs/development/evidence/2026-09-08-reader-persistence-replay.py`
- 最终逐条记录：`docs/development/evidence/2026-09-08-reader-persistence-replay-final.json`
- 数据库回归日志：`docs/development/evidence/2026-09-08-reader-integration-tests.txt`

## 接下来

1. 完成当前数据库矩阵与候选 CI，集成本批持久化底座。
2. 收敛 Delivery 与正式绑定的核验接线，追加有版本的新核验回执并展示内容支持、定位与持久绑定；历史回执保留原义。
3. 保留二进制 Word 的明确缺口；本轮不增加 DOC/OCR 工具链。

始终不调用 WMA，不修改 V3 Prompt、Candidate Facts、原始 quote/locator 或六份冻结原件。当前真实结果仍为 94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED。
