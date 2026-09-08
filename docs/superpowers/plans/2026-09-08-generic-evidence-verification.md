# 通用 Evidence Verification 实施计划

目标：复用既有证据实体，以一个有版本的公共核验边界报告内容支持、声明范围和绑定；保留同一真实 Corpus 的 94 条既有通过行为，使新增格式无需修改业务核心。

依据：[已确认的架构结论](D:/DeepAha/docs/development/reviews/2026-09-08-evidence-verification-architecture-review.md)、[开发顺序](../../development/2026-09-08-evidence-architecture-adoption.md)。用户已要求在合适阶段实施，不新增逐步审批或固定子 Agent 流程。采用现有 Python/Pydantic/PostgreSQL/对象存储，不引入新服务或模型调用。

本计划实施状态：IN_PROGRESS。首批 PR #10 已合入主线 `22b9cb8`；批次 A 已实现并完成影子逐条回放，独立复核与候选 CI 在交付记录中追加。B/C 尚未完成，不能把 Reader 文本位置映射当成持久 EvidenceRef。较长分支仅作既有功能移入和兼容性参考，不把其全量类型失败带进主线。

## 不变量

- 六份真实输入、原始 quote、Candidate Fact、V3 Prompt、Schema 和既有人工决定不改写。离线使用固定案例 `01a07fb6-4415-76bc-a14c-c6422b84cb0e`，不再次调用 WMA。
- `FOUND` 与正式绑定、`SUPPORTED` 与批准分开。30 条 Word 的已保存读回可证明已有内容命中；不可由诊断输出伪造生产 Reader 可靠性或清除 `human_verify: true`。
- 不同文字、否定词、日期、原文空格、跨岗位/跨格边界不等价；不使用语义相似或全局去空白。
- 原件 Hash、解析器/比较规则版本和范围回放均可核对；没有可靠读取时不能把未找到判成引文错误。
- 工程验证不代替真人事实审批和发布资格。旧回执只读，新核验结果追加。

## 批次 A：公共核验边界及行为保留的 Adapter

新建 `backend/src/deepaha/evidence_verification/`：

| 文件 | 职责 |
| --- | --- |
| `contracts.py` | 冻结的原件输入、Reader 身份、文本片段/来源范围、内容/声明定位/歧义/精度与统一结果 |
| `registry.py` | 显式受控注册；新读取按 media type，历史回放按名称/版本/parse contract 精确选择；缺失版本明确不可验证 |
| `verifier.py` | 身份/Hash、范围内连续字面匹配、原始位置去重及公共裁决；不识别格式、事实字段或资格结论 |
| `adapters/html.py` | DOM 范围及可追溯比较投影；迁移现有 `html-quote-c14n/1`，保留原文与投影偏移区别 |
| `adapters/pdf.py`、`adapters/spreadsheet.py` | 复用现有受限读取；页/行列范围及读取完整性说明；不裁决事实 |

- [x] 先为错误原件、错误范围、文字差异、重复位置、Reader 不完整和不支持格式建立结果断言。未支持与可靠 NOT_FOUND 必须不同；伪造 Reader/锚点不得通过注册边界。
- [x] 完成纯输入输出的共同表示与核验。一次运行对每份原件/Reader 版本只读取一次；同一位置的多个投影不能重复计数。
- [x] 用 HTML 测试保留四条单元格折行，通过真实父范围解释内联 selector；不把规范化后的 offset 当成原文本位置。
- [x] 将 PDF/XLSX 的格式读取放到适配器，保留原页/行/单元格精度和现有资源限制。读取器输出不包含 PASS/FAIL 或业务事实判断。
- [x] 对冻结 Corpus 逐条比较，记录引用身份、原结果、新内容支持、定位/歧义和原因；验证 94 条无回归，30 条仍真实表达缺口。

本批先用离线/影子调用建立可检查结果，不在新旧绑定结果不一致时提前替换正式链路。

## 批次 B：现有 DocumentBlock/EvidenceRef 的一次性兼容扩展

涉及 `contracts` 中新增版本化通用锚点契约、`documents/blocks.py`、`models.py`、`service.py`、`parser.py` 及新的 `backend/migrations/versions/` 文件。沿用已有 UUID、Document parse identity、block hash 和 evidence binding hash；不改写已版本化 migration。

- [ ] 新增一种通用文本片段与 Reader 锚点种类。统一外壳严格记录 Reader namespace/version、anchor schema、原范围 payload；格式 payload 必须经对应 Adapter 验证，不允许任意 JSON 自称有效。
- [ ] 数据库继续约束文档/原件/块/引用的一致关联、Hash、父块顺序和不可变性。新种类使用统一约束，未来格式不再加数据库枚举。
- [ ] 对 0.1/0.2/0.8 历史记录继续采用原加载和回放身份。新表示产生新 parse key；旧绑定或批准不能被新版本自动继承。
- [ ] 迁移编号与依赖在集成时按实际唯一 Alembic head 分配，先处理直接需要的原件/绑定桥接依赖，保持一条可回退链；不得为抢占编号改写历史文件或将未来 25 个迁移整体带入。
- [ ] PostgreSQL/Moto 集成测试覆盖旧记录、新通用块、Hash/外键/非法 payload、不可变更新拒绝、回退前置条件及模型一致性。

## 批次 C：Delivery 与正式绑定共用结果

涉及 `investigations/delivery.py`、从长分支移入的 `documents.py`/`evidence_blocks.py` 及其直接依赖、现有调查回执和审核展示。既有移入文件的完整类型检查先修复，再增加接线；不借此移入无关个人/资格功能。

- [ ] Delivery 保留 JSON/Schema、文件清单、跨文件实体与字段一致性，调用公共检查器；不再保留格式 switch 或第二套规范化。
- [ ] 正式绑定验证持久 DocumentBlock 的身份与 Hash 后，复用同一范围表示；解决四条表头和一条内联发布时间的已复现缺口。旧内容 PASS 不被改称旧绑定 PASS。
- [ ] 追加保存核验版本、表示 Hash、content support、declared locator、binding candidate/anchor、precision、ambiguity、verdict/reasons。现有历史布尔值保留原义；读旧回执不得虚构新核验维度。
- [ ] 审核页面显示内容与定位的独立状态、原定位和候选位置。无法绑定或需人工确认时保持 UNVERIFIED，现有内部材料/正式事实审批边界不变。
- [ ] 必须完成真实 Corpus 逐条回放、迁移/原件持久化/历史兼容测试，以及桌面为主、手机可读的浏览器验证，才替换原路径。

## 批次 D：扩展性证明与收尾

- [x] 用测试内新增的合成文本格式 Adapter，证明仅新增 Adapter、注册配置和测试即可读取/定位/回放；`verifier.py`、Delivery 核心、Candidate、Fact lifecycle、VerifiedFact 审批、Opportunity 的生产改动数为零。
- [ ] 错 Hash、错范围、日期/否定词变化、跨格拼接、重复位置、不完整读取、OCR 可靠性不足都有确定结果；没有强行追求 124/124。
- [ ] 执行相关纯函数/契约/数据库回归、`ruff`、完整 `mypy src tests`、Web 检查及必要浏览器链，独立代码评审后提交 PR，检查通过再合入。
- [ ] 更新实现与验证状态、保留可复现脚本和证据。低频 DOC/XLS/OCR Adapter 按后续真实收益决定投入；本计划不预先选择转换程序，不以此扩建文档取证平台。
