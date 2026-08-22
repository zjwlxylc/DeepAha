# DeepAha 系统开发路线

**状态：** `PROPOSED`  
**基线日期：** 2026-08-21  
**目标：** 用最小、连续可运行的纵向切片，逐步建立“可信发现 -> 判断 -> 行动 -> 学习”闭环，并让每一步都有可执行的退出条件。

## 1. 路线选择

本项目采用“Gate 驱动的模块化单体 + 纵向切片”，不采用一次性完整平台规划，也不采用 UI 原型先行。

原因：

- 项目最大风险是资格、证据和变化处理不可信，而不是页面数量不足。
- 数据对象和规则一旦设计错误，会同时污染采集、推荐、提醒、反馈和商业化。
- 单体内部保持明确模块边界，比早期微服务更容易事务一致、回放、调试和快速迭代。
- 每个阶段都能形成独立可验收成果，失败时可以收敛，而不是继续扩大范围。

## 2. 全局阶段图

```text
Phase 0 工程基础
    ↓
Phase 1 领域契约与原始证据
    ↓
Phase 2 采集与文档理解
    ↓
Phase 3 Opportunity 归并、版本与变化
    ↓
Phase 4 规则、资格与评估
    ↓
Phase 5 公开可信层
    ↓
Phase 6 画像、匹配与个人行动
    ↓
Phase 7 反馈、审核与双轨验证
    ↓
Phase 8 提醒、计划与多端承接
    ↓
Phase 9 稳定性、Beta 与商业 Gate
```

横向能力“安全与隐私、可观测性、数据质量、评估可复现”从 Phase 0 开始贯穿，不作为上线前补丁。

阶段箭头表达真实的代码、迁移与契约依赖顺序，不表示下一 Phase 必须等待上一 Phase 的真实环境
Release Qualification。每个阶段的实现状态、Engineering Gate、Release Qualification 和契约成熟度
独立记录：Engineering Gate `CLOSED` 后允许下一 Phase 正常开发；Release Qualification 未完成只
阻塞对应正式发布、真实环境完成声明和契约 `STABLE`。下游仍须基于实际依赖提交完成兼容验证，
但不得形成 `BLOCKED_BY_PHASE2` 或 `IMPLEMENTED_PENDING_*` 级联状态。

## 3. 阶段定义

### Phase 0：工程基础

**目的：** 创建可重复安装、可测试、可构建的最小仓库骨架。

**范围：**

- Python/FastAPI 后端骨架、Next.js Web 骨架。
- 统一配置、结构化日志、健康检查和版本信息。
- Python 与 TypeScript 的格式、静态检查、单元测试和 CI。
- 根级开发命令和本地启动说明。

**退出条件：**

- 新环境可按 README 完成依赖安装。
- 后端健康测试通过，Web 首页组件测试和生产构建通过。
- 一条根级验证命令能完整运行静态检查、测试和构建。
- 没有接入数据库、LLM、采集器或业务页面。

### Phase 1：领域契约与原始证据

**目的：** 锁定最小数据语言，建立不可变原始证据链。

**范围：**

- `Source`、`RawArtifact`、`Document`、`Opportunity`、`EvidenceRef` 的 v0.1 Schema。
- PostgreSQL 18 数据库、迁移框架和约束。
- S3 兼容对象存储接口和本地开发实现。
- 一个固定官方样本的入库、哈希去重和证据定位。

**退出条件：**

- 同一内容重复导入不会创建第二份 RawArtifact。
- 原始字节、抓取时间、来源 URL、内容哈希和对象键可以共同复现输入。
- Document 与 Opportunity 在模型和数据库中明确分离。
- Schema、数据库迁移和契约测试一致。

### Phase 2：采集与文档理解

**目的：** 从登记官方入口获得可审计的 HTML、PDF 和 Excel 观察，并生成带结构化定位的可回放 Document。

**范围：**

- 领域契约 v0.2：`SourceEndpoint`、`CaptureObservation`、`ParseAttempt`、机会类型扩展和 Evidence Locator v0.2。
- Source Registry、来源使用边界、限速、有界重试、条件请求和观察记录派生的源健康。
- 同步 HTTP 采集应用服务和显式 CLI；本阶段不增加调度器、队列、Redis 或浏览器默认路径。
- HTML、文本型 PDF、XLSX 确定性解析器及统一 Document/派生文本输出。
- 低置信度、格式不支持与永久失败保存稳定状态和原因码；不提前建设完整审核系统。
- 十个代表性官方入口的显式 live 观察窗口；默认测试只使用固定夹具。

**Engineering Gate 退出条件：**

- 相同内容的两次抓取保留两条 CaptureObservation，只复用一个 RawArtifact。
- 固定 HTML、PDF、XLSX 能定位回 DOM 文本、PDF 页内文本或 Excel 单元格范围并校验片段哈希。
- 网络失败可重试，永久采集/解析失败可审计且不会丢失或覆盖原始证据。
- v0.1 与 v0.2 Schema、迁移、ORM 和契约测试一致；固定样本回放得到确定性相同结果。
- 默认 CI 不访问实时来源、浏览器或模型；live 观察必须显式开启。
- 代码审查、安全扫描和 Phase 2 scope 检查不存在未解决的工程 blocker。

**Release Qualification：**

- 10 个代表性官方入口完成至少 24 小时、五轮策略间隔、至少 50 个最终结果的显式观察，
  `SUCCEEDED + NOT_MODIFIED` 有效率达到 `>=98%`，并有源健康和维护成本记录。
- 精确最终候选在新鲜副本完成统一验证，最终候选远程 CI 成功。
- 未达到这些真实环境条件前不得宣称 Phase 2 真实环境验收完成，v0.2 不得标记 `STABLE`；
  但该状态不阻塞 Phase 3 正常工程开发和独立 Engineering Gate 判断。

Model Gateway、Playwright、Docling 和 OCR 不是 Phase 2 默认范围；只有固定失败样本证明确定性路径不足时，才通过独立 spec 评估。Opportunity Resolver、版本和变化仍严格属于 Phase 3。

### Phase 3：Opportunity 归并、版本与变化

**当前状态（2026-08-22）：** 实现状态 `IMPLEMENTED`；Engineering Gate `CLOSED`；
Release Qualification `NOT_STARTED`；v0.3 契约成熟度 `IMPLEMENTED`。Phase 2 closing commit 已
完整纳入并重新执行契约、迁移、Resolver、identity replay、安全与 scope 验证。该结论只允许
后续阶段正常工程开发，不授权合并、发布或把 v0.3 标记为 `STABLE`。

**目的：** 把多文档组织成稳定机会，追踪更正、延期和状态变化。

**范围：**

- Opportunity Resolver、稳定 public_id、别名与合并审计。
- OpportunityVersion、OpportunityEvent 和字段级差异。
- 更正优先级、附件替换、延期、取消和状态机。

**Engineering Gate 退出条件：**

- 公告正文、岗位表和更正通知可归并为一个 Opportunity。
- 历史版本、旧链接、收藏引用和证据关系不因合并丢失。
- 代表性更正与延期样本能产生正确的高影响变更事件。
- 任意公开状态能从版本与事件重新计算。

**Release Qualification：**

- 尚未开始真实 Gold Opportunity、真实来源变化识别、新鲜副本或生产相似环境候选验证。
- 合成 Resolver 样本与常规 CI 只属于 Engineering Gate 证据，不转换成真实准确率结论。
- 只有对应 Release Qualification 明确为 `QUALIFIED` 后，v0.3 才可另行评估 `STABLE`。

### Phase 4：规则、资格与评估

**目的：** 形成系统最核心的可审计资格能力。

**当前状态（2026-08-22）：** 实现状态 `IMPLEMENTED`；Engineering Gate `CLOSED`；Release
Qualification `NOT_STARTED`；v0.4 契约成熟度 `IMPLEMENTED`。Phase 3 closing commit 已完整
合入，兼容审查、本地全量验证与精确候选 SHA 远程 CI 已通过。这些状态独立记录，不继承
Phase 2/3 的 Release Qualification 状态，也不授权合并、发布或把 v0.4 标记为 `STABLE`。

**范围：**

- 规则 DSL、Rule Compiler、Eligibility Engine 和资格四态。
- 专业目录、学历、毕业年份、年龄日期和缺失字段的第一组确定性规则。
- Golden Dataset、100 个版本化模拟画像和批量回放。
- MatchSnapshot、组件版本和证据链。

**Engineering Gate 退出条件：**

- LLM 语义推断不能单独产生 `INELIGIBLE`。
- 同一数据集与版本重复评估得到相同输出。

**Release Qualification：**

- 在版本固定、人工标注的适用 Golden Dataset 上，所有硬结论证据可追溯率达到计划目标 `100%`。
- `INELIGIBLE` 误杀率达到计划门槛 `<=0.5%`，严重错误逐例复盘；合成画像结果不能替代该结论。

当前固定合成数据只证明受控边界样本的确定性回放和零意外错误否定；它不证明真实
`<=0.5%` 指标、真实用户价值、真实环境资格或发布就绪。

### Phase 5：公开可信层

**目的：** 让用户在提交画像前看见系统掌握了什么以及信息是否可信。

**当前状态（2026-08-22）：** 实现状态 `IMPLEMENTED`；Engineering Gate `CLOSED`；Release
Qualification `NOT_STARTED`；Phase 5 Public API Contract Maturity `IMPLEMENTED`。工程证据使用
3 条许可安全合成机会；真实 Gold 数量为 0，不能据此宣称 200 条真实 Gold 或发布就绪。

**范围：**

- 200 个 Gold 机会驱动的只读公开索引和详情页。
- 官方入口、当前状态、发布时间、截止时间、最后核验时间和变化历史。
- 移动响应式 Web/PWA 壳、搜索与筛选的最小实现。
- 从公开机会进入“判断我是否适合”的入口。

**Engineering Gate 退出条件：**

- 页面不显示未经画像计算的个人资格或虚构匹配百分比。
- 用户能从任何硬信息回到官方证据。
- 公开索引仅服务 Gold 样本，不扩成无限公告流。

**Release Qualification：**

- 200 个真实 Gold 机会的公开可信字段完整率达到计划要求 `100%`，官方回链、核验时间和变化
  历史在真实候选环境可复现。

### Phase 6：画像、匹配与个人行动

**目的：** 将可信机会转换为少量、解释充分、可行动的个人结果。

**当前状态（2026-08-22）：** 实现状态 `IMPLEMENTED`；Engineering Gate `OPEN`，等待 stacked
draft PR 与最终精确 SHA 的七个远程 CI jobs；Release Qualification `NOT_STARTED`；v0.5 契约
成熟度 `IMPLEMENTED`。本地证据只含 2 个合成画像、3 个合成机会、0 真人和 0 真实 Gold。

**范围：**

- 最小 UserState、渐进画像和版本记录。
- Eligibility 与 Ranking 分离的 Match 流程。
- 未来 90 天结果、3 个优先机会、缺失字段和风险说明。
- 官方跳转、保存、材料计划和行动状态。

**Engineering Gate 退出条件：**

- 删除软偏好不会改变硬资格。
- 用户能理解每个结论的满足项、冲突项、缺失项和官方证据。
- 画像、排序和行动按服务端身份与用途授权隔离，写操作幂等且可审计。
- 版本绑定、90 天窗口、最多 3 条、浏览器流程和失败恢复有可复现工程证据。

**Release Qualification：**

- 最小画像完成率达到计划门槛 `>=60%`，不依赖强迫字段。
- 真人能理解四态、证据和下一步，认知负担在受治理研究中可接受。
- 端到端薄链路从公开浏览走到至少一个真实高意图动作。

固定合成 fixture、CI 和浏览器测试只属于 Engineering Gate，不能形成上述真人结论。

### Phase 7：反馈、审核与双轨验证

**目的：** 把用户回复变成候选证据，而不是直接污染线上规则。

**范围：**

- FeedbackEvent、审核状态、证据补充、裁决和发布关联。
- Review Queue、审核 SLA、冲突升级和审计日志。
- 100 模拟画像与 20–30 真人设计伙伴的并行实验。

**退出条件：**

- 原始反馈、批准标签和线上版本严格分离。
- 用户纠错不会直接改变线上规则或历史 MatchSnapshot。
- 真人反馈与模拟结果使用不同指标和结论语言。
- 首轮复盘只批准一个最关键改进方向，避免多变量混淆。

### Phase 8：提醒、计划与多端承接

**目的：** 证明“替我盯着”能带来真实行动，而不是通知噪声。

**范围：**

- 新机会、截止临近、重大更正和关注机会事件提醒。
- 事务性 Outbox、幂等发送、退避重试、失败审计和用户频率控制。
- 日历/材料计划；小程序承接今日、机会、计划和我的。

**退出条件：**

- 重复任务不会重复发送同一提醒。
- 用户能关闭个性化推荐和通知渠道。
- 高影响提醒打开率与投诉/关闭率同时纳入评估。
- Web/PWA 与小程序共享 API、状态和审计记录。

### Phase 9：稳定性、Beta 与商业 Gate

**目的：** 在不牺牲可信度的前提下验证区域运行、真实行动与付费。

**范围：**

- 100–300 高价值源、性能、备份恢复、安全和隐私请求演练。
- 200–500 人封闭 Beta、分层指标和版本冻结。
- 价格实验、高校小规模渠道实验；自然排序与商业展示隔离。
- Gate F 合规扩张核验：招聘服务边界、AI 内容标识、数据保护、内容使用和机构责任。

**退出条件：**

- 数据、资格、模拟、真人行动和商业 Gate 分别有可复现证据。
- 浙江源 SLO 连续达标后才规划第二个深覆盖区域。
- 真实付费来自持续判断、变化监控和行动支持，不来自公告付费墙。
- 未过 Gate 时明确继续打磨或 No-Go，不用营销扩大失败。
- 面向公众或机构扩大前完成与实际功能相符的合规核验；Blueprint 和内部检查不得替代法律意见。

## 4. 十四天验证切片

十四天不是完成全平台，而是 Blueprint 的经营验证节奏参考；仓库当前已经按独立 Gate 完成 Phase 0–1。经明确授权可在隔离分支做受控堆叠候选实现，但不得据此表绕过 Gate、合并或发布顺序：

| 时间 | 重点 | 计划产出 | 验收方式 |
| --- | --- | --- | --- |
| D1–2 | Phase 0 | 工程骨架、CI、开发命令 | 全新环境验证 |
| D2–5 | Phase 1 最小切片 | v0.1 契约、一个真实样本、原始证据 | 重复导入与证据回放 |
| D4–8 | Phase 2–4 最小切片 | 一个 Opportunity、首组规则、资格四态、批量评估 | 固定夹具回放 |
| D7–10 | Phase 5–6 薄界面 | Gold 机会索引、最小画像、3 个结果、官方跳转 | 真人完整走通 |
| D9–12 | Phase 7 | 画像库、反馈入队、真人设计伙伴材料 | 结构化反馈与审计 |
| D13–14 | 双轨复盘 | 错误分类、版本差异、下个 Slice | 只批准一个改进方向 |

十四天范围中的后续阶段只实现维持一条纵向链路所需的最小能力，不等于这些阶段整体完成。

## 5. 文档生成节奏

- Phase 0、Phase 1 已有详细 spec、plan 和关闭证据。
- Phase 2 已生成独立设计与实施计划，引用 Blueprint v1.2、基线协调记录和领域契约 v0.2。
- Phase 3 已生成独立 spec/plan、实现和 Engineering Gate 证据；Phase 4 已生成独立 spec/plan、
  实现和 Engineering Gate 证据。Phase 5–9 启动前分别生成独立 spec 和 plan，并引用本路线与
  当时可用的上游契约，独立记录 Engineering Gate 与 Release Qualification。
- 任一阶段发现隐藏复杂度时，拆成可独立验收的子阶段；不得扩大一个计划直到所有系统都包含在内。
- 每个阶段验收后更新本文状态和证据链接，不重写历史结果。

