# DeepAha Blueprint v1.2 基线协调设计

> 状态：`IMPLEMENTED`
>
> 日期：2026-08-21
>
> 适用范围：Phase 2 及后续新设计；已经关闭的 Phase 0、Phase 1 结果保持其原始证据与契约版本
>
> 本文记录已批准的文档治理和阶段映射，不表示 Phase 2 功能、指标、商业结果或合规结论已经实现或验证。

## 1. 决策摘要

用户在完整评估后授权执行以下协调结果：

1. `文档2/DeepAha_青年机会智能系统_Blueprint_v1.2.docx` 晋升为当前产品、业务和验证策略的上位 Blueprint。
2. `文档2/DeepAha_创业投资人视角审查_v1.0.docx` 是风险、融资与验证假设输入，不是软件需求或已证实的市场结论。
3. `文档2/DeepAha Opportunity Intelligence Engine 技术架构设计 V1.0.md` 是技术候选与调研输入；其中的组件分级、star 数、版本和“直接采用”表述不能覆盖阶段 spec、已验证代码或开源准入结果。
4. Blueprint v1.0.1 降为历史基线；Phase 0、Phase 1 在其约束下形成的已验证结果不因上位文档升级而失效。
5. Phase 2 先完成领域契约 v0.2 的兼容扩展，再进入实时采集与文档理解；不得借基线升级进入 Phase 3。

## 2. 文档权威层级

发生冲突时按以下顺序处理：

1. 用户当前任务的明确要求。
2. 根目录 `AGENTS.md`。
3. Blueprint v1.2 的产品、业务、验证与治理决策。
4. 已关闭 Gate 的版本化契约、迁移、测试和验证证据；新 Blueprint 不追溯改写历史事实。
5. `docs/development/` 当前开发基线和已批准阶段 spec/plan。
6. Blueprint v1.0.1 及其他既有研究材料，用于补充 v1.2 未改变的内容。
7. 投资人审查和技术架构设计，分别作为验证/风险输入和技术候选输入。

若 v1.2 与已实现行为不一致，必须通过新契约版本、迁移和测试演进，不能只改文档或静默改变旧数据含义。

## 3. 已批准决策 D8–D12

| ID | 决策 | 已批准方案 | 主要边界 |
| --- | --- | --- | --- |
| D8 | 上位基线 | Blueprint v1.2 自 Phase 2 起成为当前上位基线 | 不重写 Phase 0/1 历史验收结论 |
| D9 | 机会类型扩展 | v0.2 增加 `COMPETITION`、`RESEARCH_PROGRAM`、`SCHOLARSHIP`、`YOUTH_DEVELOPMENT_PROGRAM` | 先迁移、Schema、ORM、契约测试一致，再用于样本；可信培训和普通民企仍不进入本次扩展 |
| D10 | 实时捕获语义 | 新增独立 `CaptureObservation`；每次网络尝试保留观察，`RawArtifact` 继续按内容去重 | 相同字节的新抓取不能被去重规则吞掉；失败观察不伪造 RawArtifact |
| D11 | 证据定位演进 | Evidence Locator v0.2 使用带版本的判别联合，兼容读取 v0.1 `{kind,value}` | 新 HTML/PDF/Excel 定位不得把结构化坐标塞进不透明字符串 |
| D12 | Phase 2 技术边界 | 同步应用服务和显式命令先行；HTTP 默认，Playwright 仅动态兜底；解析器经适配器和固定样本验收 | 不增加 Celery、Valkey、Redis、pgvector、生产云、Resolver、规则、用户或业务页面 |

## 4. v1.0.1 到 v1.2 的开发差异

| 变化 | 开发影响 | 阶段映射 |
| --- | --- | --- |
| 机会范围加入比赛、科研、奖学金和青年成长计划 | 受控枚举和 Golden Dataset 必须版本化扩展 | Phase 2 首个契约任务；Gold 业务覆盖仍由后续阶段证明 |
| 强调用户不是可出售的数据资产 | 补充隐私、商业隔离和机构交付边界 | 横向治理；不新增用户系统 |
| 早期商业重点转向高校机会情报模块/试点 | 作为 Phase 9 商业验证候选 | Phase 2 不增加 `InstitutionAccount` 或商业展示实体 |
| 六层资产与写入时智能被强化 | 保持原始证据、结构化派生、版本历史和评估语料分离 | Phase 2 只建立采集观察与文档证据层 |
| 五道 Gate 扩展为六道，增加合规扩张 Gate F | 更新质量与发布路线 | 真实公开服务、机构试点或规模扩张前执行，不是 Phase 2 完成证明 |
| 增加成本和交付效率指标 | 定义可观测字段和证据口径 | Phase 2 记录源维护与解析成本；商业指标延期到 Phase 9 |
| 十二周双轨节奏 | 仅作为经营节奏参考 | 不覆盖仓库 Gate 顺序，不把已完成 Phase 1 重排为未来工作 |

## 5. 新材料中不直接采纳的内容

以下内容没有获得实现授权：

- 把 Docling、Celery、Valkey、pgvector 或其他候选组件直接加入依赖。
- 因技术架构文档的建议重构当前仓库目录。
- 在 Phase 2 实现 Opportunity Resolver、OpportunityVersion、变化检测、资格规则或模型最终裁决。
- 把投资人评分、市场规模、定价、融资节奏或机构付费假设写成发布证明。
- 把 `InstitutionAccount`、`CommercialPlacement` 或高校后台提前加入领域契约。
- 把 200 个 Gold 机会的经营目标压缩成 Phase 2 解析器的完成条件。

## 6. Phase 2 前置调整

Phase 2 必须按以下顺序开始：

1. 发布兼容的领域契约 v0.2 提案，并用 TDD 同步 Pydantic、JSON Schema、数据库迁移、ORM 和契约测试。
2. 以 `CaptureObservation` 表达每次抓取成功、未变化和失败；`RawArtifact` 只表达不可变字节。
3. 建立 Source Registry、来源使用边界和同步 HTTP 采集服务；默认测试不访问网络。
4. 通过解析器适配器产生统一 Document 和 EvidenceRef v0.2；先 HTML，再 PDF 和 Excel。
5. 用固定、有许可说明的夹具和显式开启的官方源观察验证，不让实时网页决定默认 CI 成败。
6. 保存 Gate 证据后才判断 Phase 2 是否关闭；Phase 3 始终是独立 spec/plan。

## 7. 成功标准

本次基线协调只有在以下条件同时满足时才算落实：

- `AGENTS.md` 和开发文档只指向一套当前上位 Blueprint。
- v0.1 保持 `STABLE` 历史契约，v0.2 在实现验证前明确为 `PROPOSED`。
- D8–D12 在 Phase 2 spec 和 plan 中有可追踪任务或明确延期。
- Phase 2 spec 不宣称任何采集、解析、指标或合规结果已经完成。
- 新材料原件、来源路径和角色被记录，但候选技术不因文档措辞自动获批。
