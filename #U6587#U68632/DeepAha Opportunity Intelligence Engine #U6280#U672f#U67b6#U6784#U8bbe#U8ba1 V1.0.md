# DeepAha Opportunity Intelligence Engine 技术架构设计 V1.0

**项目：** DeepAha 青年机会智能系统  
**核心引擎：** Opportunity Intelligence Engine  
**版本：** V1.0  
**日期：** 2026-08-21  
**状态：** 技术实现基线  
**适用阶段：** Opportunity Lab → 12 周 MVP → 封闭 Beta  
**上位基线：**《DeepAha 青年机会智能系统 Blueprint v1.0.1》

---

## 0. 文档定位

本技术架构设计不重新定义产品，而是把 Blueprint 已确定的产品逻辑工程化。

Blueprint 已确定：

> DeepAha 不是招聘信息平台，也不是 AI 聊天机器人，而是一套持续监控真实公开世界、维护 Opportunity 状态、结合个人条件作出可解释判断，并通过真实反馈不断改进的个人机会情报系统。

同时已经明确：

- 外部大模型 API + 确定性规则 + 持久化数据；
- 不训练基础大模型；
- 资格判断与推荐排序严格分离；
- INELIGIBLE 不允许由 LLM 单独产生；
- Opportunity、历史版本、官方证据、UserState、Feedback 和 Evaluation 是长期资产；
- 公开机会库与个人行动台共享同一智能核心；
- 生产主链不要过度 Agent 化。

因此 V1.0 的技术任务只有一个：

> **建立一套可靠、可追溯、可回放、可持续学习的 Opportunity Intelligence Engine。**

---

# 1. V1.0 最重要的架构结论

经过本轮 GitHub 实际尽调，V1.0 不采用“开源项目拼装”的路线。

最终采用：

> **DeepAha 自有领域核心 + 少量高质量基础开源组件。**

系统中真正属于 DeepAha 的部分必须自己开发：

| 必须自研 | 原因 |
|---|---|
| Opportunity 数据模型 | 决定系统如何理解“机会” |
| Opportunity Resolver | 决定多个公告、附件、更正是否属于同一机会 |
| Opportunity Version / Event | 构成真实机会历史 |
| Rule DSL / Rule Compiler | 资格判断核心 |
| Eligibility Engine | 高风险决策核心 |
| UserState / 青年画像模型 | 用户理解核心 |
| Synthetic Youth Persona | 实验资产 |
| Ranking Feature Model | “为什么现在值得行动” |
| Feedback / Adjudication | 学习闭环核心 |
| Evaluation / Release Gate | 系统可信度核心 |
| MatchSnapshot | 推荐结果可复现核心 |
| Opportunity Learning Loop | 长期数据壁垒 |

开源只解决已经被行业充分解决的基础问题：

> 浏览器、文档解析、向量检索、任务队列、缓存。

这意味着未来即使全部替换 LLM、数据库扩展或开源组件，**DeepAha 的领域数据和判断逻辑仍然完整存在。**

---

# 2. 开源项目准入制度

以后任何开源项目进入 DeepAha，必须同时通过六项检查。

### G1：业务耦合度

它必须真正解决 DeepAha 当前存在的问题。

“看起来像 AI”“也是推荐系统”“也是招聘产品”均不构成采用理由。

### G2：项目质量

重点检查：

- 维护主体；
- 最近提交；
- Release；
- 文档；
- 测试；
- 社区；
- Issue；
- 安全维护；
- 生产案例。

Star 只是辅助指标，不是采用理由。

### G3：License

必须：

- 明确；
- 可审查；
- 满足商业使用要求。

无 License 的仓库原则上不得直接复制代码进入生产系统。

### G4：可替换性

所有外部核心组件必须通过 DeepAha 自有 Adapter 接入。

禁止：

> DeepAha 的领域模型被某个开源框架的数据模型反向绑架。

### G5：收益大于复杂度

如果引入一个项目节省 3 天开发，却增加长期部署、升级、兼容和理解成本：

**不采用。**

### G6：不让渡核心能力

Opportunity、Rule、Evidence、UserState、Match、Feedback、Evaluation 永远由 DeepAha 自己掌握。

---

# 3. GitHub 尽调后的重要修正

这次实际查看仓库以后，前期判断需要作三项修正。

## 3.1 RecruitGPT：从“重点复用”降为“不采用”

RecruitGPT 的思路确实与候选人—岗位多阶段匹配相似，README 包括 BGE、Cross Encoder、Knowledge Graph 和 LLM Explanation。

但实际仓库截至本次尽调：

- Star 仅约 2；
- Fork 约 1；
- 仓库规模很小；
- GitHub 元数据没有识别到 License；
- 项目非常新；
- 大量路线建立在自己训练 BGE、小模型和 GPU pipeline 上。

这与 DeepAha 当前“API-first、不训练基础模型、以官方证据和资格规则为核心”的技术路线并不紧密。

**决策：D级，不复用代码。**

最多参考“召回 → 重排序 → 解释”的思想。

---

## 3.2 Resume-Job-Matching-System-v1：取消候选资格

实际仓库：

- 0 Star；
- 0 Fork；
- 无 License；
- 2026 年才创建；
- 规模很小。

**决策：D级，完全不进入架构。**

---

## 3.3 Microsoft GraphRAG：质量很高，但 V1 仍然不用

Microsoft GraphRAG 约 3.5 万 Star、MIT License，项目质量显然远高于前两者。

但项目 README 已明确说明：

> GraphRAG 是 research project，目前 largely in maintenance mode，不再接受新功能开发，并提醒 indexing 成本可能很高。

更重要的是：

DeepAha V1 的核心问题不是：

> “如何从一个超大文本库进行图谱式问答？”

而是：

> “一个官方公告发生了什么变化、资格规则是什么、它对某个人意味着什么？”

V1 使用 PostgreSQL 的关系数据 + relation edge + pgvector 已足够。

**决策：C级，只研究方法，不引入生产系统。**

这是本轮尽调最能体现选型原则的例子：

> **高质量开源 ≠ 应该采用。**

---

# 4. 总体架构

```text
                         ┌────────────────────────────┐
                         │       PUBLIC WORLD         │
                         │ 官方网站 / PDF / Excel ... │
                         └─────────────┬──────────────┘
                                       │
                              SOURCE MONITORING
                                       │
              ┌────────────────────────▼───────────────────────┐
              │             INGESTION LAYER                   │
              │ Source Registry                               │
              │ HTTP Collector                                │
              │ Playwright Fallback                           │
              │ Raw Artifact Snapshot                         │
              └────────────────────────┬───────────────────────┘
                                       │
              ┌────────────────────────▼───────────────────────┐
              │          DOCUMENT INTELLIGENCE                │
              │ Native HTML / XLSX Parser                     │
              │ Docling PDF / DOCX / Image Parser             │
              │ Evidence Locator                              │
              │ LLM Structured Extraction                     │
              └────────────────────────┬───────────────────────┘
                                       │
              ┌────────────────────────▼───────────────────────┐
              │       OPPORTUNITY INTELLIGENCE CORE           │
              │                                               │
              │ Opportunity Resolver                          │
              │ Opportunity Version / Event                   │
              │ Rule Compiler                                 │
              │ Revision / Change Detection                   │
              │ Evidence Graph                                │
              └───────────────┬───────────────────────────────┘
                              │
                     ┌────────▼────────┐
                     │ ELIGIBILITY     │
UserState ──────────►│ ENGINE          │
                     │ 四态资格判断     │
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │ CANDIDATE       │
                     │ RETRIEVAL       │
                     │ FTS + pgvector  │
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │ RANKING ENGINE  │
                     │ 可解释优先级      │
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │ EXPLANATION &   │
                     │ ACTION PLANNER  │
                     └────────┬────────┘
                              │
             ┌────────────────▼────────────────┐
             │      USER EXPERIENCE           │
             │ Web/PWA │ Mini Program         │
             │ 今日行动 │ 机会库 │ 计划 │ 我的 │
             └────────────────┬────────────────┘
                              │
                        ACTION / FEEDBACK
                              │
             ┌────────────────▼────────────────┐
             │      LEARNING & GOVERNANCE     │
             │ Feedback Pipeline              │
             │ Human Review                   │
             │ Evaluation                     │
             │ Shadow Replay                  │
             │ Release Gate                   │
             └─────────────────────────────────┘
```

这不是“LLM 主导架构”。

正确理解是：

> **数据库保存世界，规则裁决资格，排序判断优先级，大模型理解复杂语言，人最终决定行动。**

---

# 5. 软件架构：模块化单体，而不是微服务

V1.0 明确采用：

> **Modular Monolith + Async Workers**

而不是微服务。

原因是 DeepAha 当前核心困难在：

- 数据契约；
- 规则；
- Opportunity Resolution；
- 评估；
- 产品验证。

而不是百万 QPS。

微服务现在只会增加：

- API 通信；
- 分布式事务；
- 部署；
- 日志追踪；
- 数据一致性；
- 开发调试

的额外成本。

### V1 逻辑模块

```text
deepaha-core
│
├── source
├── ingestion
├── document
├── opportunity
├── evidence
├── taxonomy
├── rules
├── eligibility
├── profile
├── retrieval
├── ranking
├── explanation
├── action
├── feedback
├── review
├── evaluation
├── notification
└── model_gateway
```

业务模块彼此有清晰边界，但首先运行在同一个 Backend 中。

未来只有当：

- 性能；
- 团队规模；
- SLA；
- 数据隔离

产生真实需求时才拆服务。

---

# 6. 数据基础设施

## 6.1 PostgreSQL：唯一业务事实源

V1 使用 PostgreSQL 17/18。

保存：

- Opportunity；
- Version；
- Rule；
- Evidence；
- UserState；
- MatchSnapshot；
- Feedback；
- Review；
- Evaluation。

### 原则

> PostgreSQL 是 Source of Truth。

Valkey、向量索引、LLM 上下文、缓存均不得成为事实源。

---

# 7. pgvector：确定采用

DeepAha 确实需要语义检索，例如：

- “人工智能”与“AI”；
- 专业名称语义候选；
- 岗位/政策描述相似性；
- Opportunity 去重候选；
- 兴趣与机会候选召回。

pgvector 与 PostgreSQL 原生共存，因此没有再增加一套独立向量数据库。

截至尽调时约 2.2 万 Star，项目持续维护；许可证为宽松的 PostgreSQL 风格许可。 

**决策：A级，直接采用。**

但它只能：

> 找“可能相似”。

不能：

> 判断“是否符合资格”。

硬资格永远由 Rule Engine 裁决。

---

# 8. Opportunity 数据模型

这是系统最重要的自研资产。

## 8.1 一个网页不等于一个 Opportunity

例如：

```text
6月1日  招聘公告
6月3日  岗位附件
6月8日  专业目录补充
6月15日 更正公告
6月20日 报名延期
```

不能产生 5 个 Opportunity。

必须形成：

```text
Opportunity OPP-2026-ZJ-XXXX

V1 招聘公告
V2 岗位附件
V3 专业补充
V4 更正
V5 延期
```

---

## 8.2 Opportunity 核心对象

```text
Opportunity
 ├─ stable_public_id
 ├─ type
 ├─ issuer
 ├─ region
 ├─ title
 ├─ lifecycle_status
 ├─ open_at
 ├─ close_at
 ├─ official_entry
 ├─ current_version
 └─ confidence
```

同时建立：

```text
Opportunity
 ├── OpportunityVersion[]
 ├── OpportunityEvent[]
 ├── Evidence[]
 ├── RuleSet[]
 ├── Document[]
 └── Alias[]
```

---

# 9. 原始证据架构

DeepAha 不是只保存“AI 解析结果”。

必须保存：

```text
Source
 ↓
RawArtifact
 ↓
Document
 ↓
DocumentBlock / TableCell
 ↓
Evidence
 ↓
Rule / Opportunity Field
```

### RawArtifact 永久保留

包括：

- URL；
- fetched_at；
- MIME；
- SHA-256；
- HTTP metadata；
- object_key。

原文件不得被后续解析覆盖。

这样才能回答：

> “2026 年 8 月 3 日系统当时为什么作出这个判断？”

---

# 10. 采集层

## 10.1 不做开放互联网爬虫

V1 不是搜索引擎。

Source Registry 保存明确审核过的：

> 官方来源。

第一阶段目标仍是约 100–300 个高价值源，而不是百万网页。

---

## 10.2 Collector 两级架构

### Level 1：普通 HTTP

默认采用：

```text
HTTP Request
→ DOM
→ Artifact
```

这是：

- 最便宜；
- 最稳定；
- 最容易维护

的方式。

### Level 2：Playwright

只有：

- JavaScript 动态加载；
- 页面必须执行脚本；
- 页面状态需要浏览器

时才启动 Playwright。

Microsoft Playwright Python 当前约 1.49 万 Star、Apache-2.0、持续活跃，仓库当前 Issue 数也很低。

**决策：A级，直接采用，但只作为动态站点 fallback。**

不是：

> 所有源都用浏览器爬。

---

# 11. 为什么 V1 不采用 Scrapy

Scrapy 是极高质量项目：

约 6.4 万 Star、BSD-3-Clause、长期维护。

但 V1 当前：

- 源是有限登记的官方来源；
- 每个 Source 有明确 fetch_policy；
- 需要保存版本和 Evidence；
- 不是大规模 Web Crawl。

因此 Scrapy 的完整 crawler framework 并没有产生足够大的额外收益。

**决策：C级，目前不采用。**

如果未来出现数万独立网站、大规模 URL frontier、分布式抓取调度需求，再重新评估。

---

# 12. 文档解析架构

这是本轮开源尽调中复用价值最高的区域。

## 12.1 不使用一个解析器处理所有格式

采取：

> **Deterministic First，Document AI Second。**

### HTML

优先：

DOM 结构解析。

### XLSX / CSV

优先：

原生结构解析。

必须保留：

```text
sheet
row
column
cell
```

因为岗位表里：

> “第 47 行第 F 列”

比 LLM 的自然语言解释更可靠。

### PDF / DOCX / 图片复杂文档

使用 Docling。

---

# 13. Docling：V1 最值得直接复用的项目

Docling 实际具备：

- PDF；
- DOCX；
- PPTX；
- XLSX；
- HTML；
- 图片；
- 表格；
- 页面布局；
- OCR；
- lossless JSON；
- 本地运行。

项目约 6.5 万 Star、MIT License，仍保持高频开发；由 IBM Research 发起，目前进入 LF AI & Data 生态。 

它解决的正是 DeepAha 一个明确而困难的问题：

> 官方公告往往不是网页正文，而是 PDF + Excel + 附件组合。

**决策：A级，直接采用。**

但是在 DeepAha 内部必须包一层：

```text
DocumentParser
   │
   └── DoclingAdapter
```

输出必须转换为：

```text
DeepAhaDocument
DeepAhaBlock
EvidenceLocator
```

而不是让业务模型直接依赖 Docling 数据结构。

---

# 14. PaddleOCR：只做条件式 fallback

PaddleOCR 约 8.8 万 Star、Apache-2.0，对中文和扫描文档非常成熟。

但是：

> 有 OCR 能力，不等于必须再增加一个 OCR 系统。

因此流程是：

```text
Native text extraction
        ↓ fail
Docling
        ↓ fail / quality insufficient
PaddleOCR fallback
```

只有真实 Gold Dataset 证明：

> Docling 对中文扫描政策材料的识别不足

才启用。

**决策：B级，条件采用。**

---

# 15. Opportunity Resolver

这是 DeepAha 必须自研的重要模块。

任务是判断：

> 新抓到的 Document 是新机会，还是旧 Opportunity 的新增版本？

流程：

```text
Document
 ↓
Exact Fingerprint
 ↓
Issuer / Title / Date / Attachment Heuristics
 ↓
FTS + Vector Candidate Recall
 ↓
Resolver Rules
 ↓
Ambiguous?
 ├─ No → 自动归并
 └─ Yes
      ↓
    LLM Candidate Analysis
      ↓
    confidence
      ↓
    Human Review when necessary
```

LLM 可以：

> 提出归并候选。

但不允许无记录地修改 Opportunity 身份。

---

# 16. Revision Engine

它负责识别：

```text
报名时间改变
专业要求改变
年龄要求改变
岗位数量改变
附件替换
地区改变
报名入口改变
公告撤回
```

变化不是简单文本 diff。

必须形成：

```text
OpportunityEvent
```

例如：

```text
event_type = DEADLINE_EXTENDED
old_value  = 2026-08-21
new_value  = 2026-08-28
evidence   = DOC-XXX#page3
impact     = HIGH
```

---

# 17. 为什么不直接采用 changedetection.io

changedetection.io 是成熟项目，约 3.3 万 Star、Apache-2.0，并保持活跃。

但它主要回答：

> “网页有没有发生变化？”

DeepAha 要回答：

> “这个变化是否属于同一机会？改变了什么业务字段？是否改变某个用户资格？是否需要推送？”

因此把 changedetection.io 放进核心链反而会形成两个平行版本体系。

**决策：C级。**

可以用于测试期对部分 URL 做外部监测比对，但不成为生产事实源。

---

# 18. Rule Engine：整个系统最高风险核心

## 18.1 资格不交给 LLM

资格状态：

```text
ELIGIBLE
LIKELY_ELIGIBLE
UNCERTAIN
INELIGIBLE
```

规则例：

```text
education.level >= BACHELOR

graduation_year IN {2026, 2027}

age_at(reference_date) <= 35

major_code IN subtree("0809")

region.hukou == "Zhejiang"

certificate EXISTS
```

---

## 18.2 Rule DSL

每一条规则至少保存：

```text
rule_id
rule_version
rule_kind
subject_path
operator
expected_value
effective_from
effective_to
evidence_id
confidence
review_status
created_by
approved_by
```

支持的 operator 应刻意保持有限：

```text
EQ
NEQ
IN
NOT_IN
GTE
LTE
BETWEEN
EXISTS
NOT_EXISTS
IN_CODE_TREE
ANY
ALL
```

不要把 Rule DSL 变成第二种编程语言。

---

# 19. Evidence-first Rule

一条高影响规则必须满足：

```text
Rule
 ↓
Evidence
 ↓
Document
 ↓
RawArtifact
 ↓
Official Source
```

如果不能回到官方原文：

> 这条规则不能成为高确定性资格裁决。

---

# 20. 专业目录问题

“专业匹配”不能仅靠 embedding。

正确顺序：

```text
官方专业代码
 ↓
官方目录树
 ↓
人工批准 Alias / Mapping
 ↓
语义候选
```

Embedding 或 LLM 最多告诉系统：

> “广告学可能属于新闻传播学类。”

它不能直接证明：

> “这个岗位官方允许广告学报名。”

---

# 21. Eligibility Engine

输入：

```text
OpportunityVersion
RuleSetVersion
UserStateVersion
EvaluationDate
```

输出：

```text
EligibilityResult

state
matched_rules[]
failed_rules[]
unknown_rules[]
missing_user_fields[]
evidence[]
```

### INELIGIBLE 的硬要求

只有：

> 至少一条经过批准的确定性硬规则与已知 UserState 明确冲突

才能得到 INELIGIBLE。

否则必须降级为 UNCERTAIN。

---

# 22. 青年画像架构

Profile 不做一个巨大的 JSON。

拆为：

```text
User
 │
 ├── ProfileCore
 │
 │    education
 │
 │    major
 │
 │    graduation
 │
 │    region
 │
 │
 ├── UserStateVersion
 │    goals
 │    constraints
 │    readiness
 │    recent_actions
 │
 └── PreferencePolicy
      stability
      growth
      mobility
      income
      public_service
```

ProfileCore 相对稳定。

UserState 是时间状态。

这让系统可以知道：

> 去年这个机会不适合你，但今年可能变了。

---

# 23. 100 个“数字分身”的真正技术位置

Synthetic Youth Persona 不进入生产用户数据库。

建立独立：

```text
Evaluation Persona Dataset
```

每个 persona 有：

```text
known_truth
must_find
should_find
must_not_reject
must_not_notify
boundary_tags
scenario_clock
```

作用是：

- 规则回归；
- 边界测试；
- 反事实排序；
- 变化回放。

它们**不负责预测真实用户点击率、留存率和付费率**。

这一边界与现有 Blueprint 完全一致。

---

# 24. Candidate Retrieval：先召回，再判断

不能让 LLM：

> “在 10 万个机会里直接给这个用户推荐 5 个。”

正确方式：

```text
ACTIVE Opportunity
 ↓
时间窗口 Filter
 ↓
地域/类别 Filter
 ↓
Eligibility Engine
 ↓
PostgreSQL FTS
+
pgvector
 ↓
Candidate Pool
```

通常产生几十个候选。

再进入 Ranking。

---

# 25. V1 Ranking Engine：暂时不训练推荐模型

这是一个非常重要的架构决定。

现在没有足够真实反馈。

如果第一版马上训练模型：

训练的只是：

> 我们自己的假设。

因此 V1 使用可解释 Feature Ranking。

例如：

```text
Priority =
    PreferenceFit
  + OpportunityValue
  + GoalAlignment
  + Urgency
  + Novelty
  + Readiness
  + SourceConfidence
  - UncertaintyPenalty
```

Eligibility 不参加加权。

它是：

> 前置 Gate。

---

# 26. 不展示“92% 匹配度”

内部可以计算标准化 score。

用户界面只呈现：

```text
今天必须处理
强烈建议
值得看看
补充信息后判断
```

以及：

> 为什么。

原因是 92% 给用户制造了不存在的统计学确定性。

---

# 27. 什么时候才训练 Ranking Model

12 周产生的约 5000 个反馈事件：

> 可以开始研究学习排序，但不代表已经可以替代生产规则评分。

生产 ML Ranking 至少需要形成：

- 足量真实曝光；
- 明确正负反馈；
- 高意图 Action；
- L3 以上真实结果；
- 不同人群覆盖。

第一候选不采用大型神经推荐系统，而是：

> LightGBM / LambdaRank 类可解释、低成本模型。

LightGBM 本身是成熟、高质量项目，约 1.87 万 Star、MIT License，并明确支持 Ranking。

**决策：B级，数据成熟后启用。**

不是 V1 MVP 依赖。

---

# 28. LLM 的准确角色

LLM 做五件事：

### A. Structured Extraction

复杂公告 → 候选结构化事实。

### B. Ambiguous Resolution

辅助判断不同 Document 是否属于同一 Opportunity。

### C. Semantic Candidate Mapping

例如专业、技能、政策概念的候选映射。

### D. Explanation

把已确定事实转成用户可理解语言。

### E. Review Assistant

帮助审核员定位冲突和缺失。

LLM 不做：

```text
最终 INELIGIBLE
最终官方资格结论
机会生命周期事实存储
日期计算
规则代码执行
在线自动学习
```

---

# 29. Model Gateway

DeepAha 自己定义：

```text
ModelGateway
```

业务代码只能调用：

```text
extract(...)
resolve(...)
map_candidate(...)
explain(...)
review_assist(...)
```

不能：

```text
OpenAIClient
DeepSeekClient
ClaudeClient
```

散落在业务代码中。

每次调用记录：

```text
provider
model
prompt_version
schema_version
temperature
input_hash
output_hash
latency
tokens
cost
related_entity
```

---

# 30. LiteLLM：保留 Adapter，不默认引入完整系统

LiteLLM 是高质量项目，约 5.7 万 Star，支持大量模型供应商、成本统计、路由和日志；核心非 enterprise 部分采用 MIT。 

它与 Model Gateway 的确存在紧密复用关系。

但其代码和功能面非常大。

因此：

### MVP

先实现：

```text
DeepAha ModelGateway
 ├── OpenAIAdapter
 └── DeepSeekAdapter
```

### 当出现以下需求

- ≥3 模型供应商；
- 自动 fallback；
- 大量 routing；
- provider quota；
- 统一 cost policy；

再接：

```text
LiteLLMAdapter
```

**决策：B级，条件采用。**

不在 MVP 部署 LiteLLM Proxy 全套基础设施。

---

# 31. 不采用 LangGraph 进入核心主链

LangGraph 本身约 4 万 Star、MIT、活跃，是高质量 Agent 工作流项目。

但是 DeepAha Blueprint 已明确：

> 生产核心应该使用可恢复工作流和状态机，而不是多个 Agent 自由对话。

因此：

**V1 不让 LangGraph 控制：**

```text
Opportunity
Rule
Eligibility
Ranking
Release
```

未来可以让它进入：

> Research Console 的长尾辅助分析。

**决策：C级。**

---

# 32. 异步任务架构

采集、解析、模型调用、变更分析和通知天然适合异步执行。

V1 使用：

> Celery。

Celery 经过长期生产验证，目前约 2.88 万 Star，并持续维护；使用 BSD-3-Clause。 

**决策：A级，直接采用。**

任务必须：

```text
idempotent
retryable
observable
version-aware
```

任务状态不能代替业务状态。

---

# 33. Valkey 替代自托管 Redis

如果需要自己托管 Redis-compatible 缓存与 broker，V1 推荐：

> Valkey。

当前约 2.69 万 Star、BSD-3-Clause、持续活跃。

用途仅包括：

- Celery broker；
- cache；
- distributed lock；
- rate limit；
- ephemeral state。

**决策：A级，直接采用。**

禁止存储：

> DeepAha 唯一业务真值。

---

# 34. Feedback Learning Loop

用户每次操作形成：

```text
ActionEvent
```

例如：

```text
VIEW
SAVE
OFFICIAL_CLICK
ADD_PLAN
APPLY
IGNORE
DISMISS_NOTIFICATION
```

用户主动反馈：

```text
FeedbackEvent
```

继续采用 Blueprint 的 L0–L5 信任等级。

流程：

```text
Raw Feedback
 ↓
Consent
 ↓
Evidence
 ↓
Confidence
 ↓
Review
 ↓
Adjudication
 ↓
Label Asset
 ↓
Offline Evaluation
 ↓
Rule / Rank / Prompt Candidate
 ↓
Shadow Replay
 ↓
Release Gate
```

**永远不存在：**

```text
用户说错了
↓
系统立刻修改所有人的规则
```

---

# 35. MatchSnapshot：推荐必须被冻结

每一次用户看到的机会判断都生成不可变：

```text
MatchSnapshot
```

保存：

```text
user_state_version
opportunity_version
rule_version
parser_version
ranking_version
prompt_version
model
evaluated_at

eligibility
priority
reasons
missing_fields
evidence
```

这样半年以后仍然能够复现：

> 为什么当时给这个用户推了这个机会。

这是 DeepAha 与普通 LLM 推荐器的重大区别。

---

# 36. 世界模型不使用 GraphRAG 才能成立吗？

可以。

V1 的 Living Opportunity State：

```text
Opportunity
Organization
Region
Major
Skill
Policy
Program
UserState
Action
Outcome
```

它们之间的关系先存在 PostgreSQL：

```text
entity_relation

source_id
relation_type
target_id
valid_from
valid_to
evidence_id
confidence
```

这样已经形成：

> 领域关系世界。

当未来出现大量：

```text
二跳
三跳
路径发现
社区发现
复杂图推理
```

并经基准测试证明 PostgreSQL 无法满足，再引入专用 Graph Database 或新一代 GraphRAG。

V1 不预先支付这种复杂度。

---

# 37. 核心数据库对象

第一阶段至少包含：

| 域 | 核心表 |
|---|---|
| Source | source / source_endpoint / source_health |
| Evidence | raw_artifact / document / document_block / evidence |
| Opportunity | opportunity / opportunity_version / opportunity_event / opportunity_alias |
| Rule | rule_set / rule / taxonomy / taxonomy_mapping |
| User | user / profile_core / user_state_version / preference_policy |
| Decision | match_snapshot / match_reason |
| Action | action_event / action_plan / notification |
| Feedback | feedback_event / review_case / adjudication |
| Evaluation | evaluation_dataset / evaluation_case / evaluation_run |
| AI | model_call / prompt_version |
| Governance | release_version / audit_log |

---

# 38. Evidence Locator

不同格式使用不同 Locator。

### HTML

```text
DOM path + text hash
```

### PDF

```text
page + block + text hash
```

### XLSX

```text
sheet + row + column + cell hash
```

### DOCX

```text
paragraph/table + index + hash
```

这件事情非常重要。

因为：

> “AI 说官方要求本科”

不够。

DeepAha 应该能够：

> 打开原文并定位到要求本科的具体证据。

---

# 39. Evaluation Engine

这是与用户产品同等重要的内部产品。

每次 Release 必须绑定：

```text
dataset_version
parser_version
resolver_version
rule_version
ranking_version
prompt_version
model_version
```

测试顺序：

```text
Component Tests
      ↓
Golden Dataset
      ↓
100 Persona Replay
      ↓
Counterfactual Tests
      ↓
Historical Replay
      ↓
Shadow Evaluation
      ↓
Human Approval
      ↓
Release
```

---

# 40. LLM-as-Judge 不作为资格真值

可以让 LLM 帮助评价：

- 解释是否清楚；
- 文案是否冗长；
- 用户是否容易理解。

但不得让：

> 同一个 LLM 既抽取规则，又给资格真值，又评价自己的结果。

资格评估必须依赖：

> Gold Rule + Human Evidence + Executable Assertion。

---

# 41. 关键技术指标

继承 Blueprint 指标：

| 指标 | MVP Gate |
|---|---:|
| 关键字段抽取准确率 | ≥97% |
| 目标新机会发现覆盖率 | ≥95% |
| 高影响变化发现率 | ≥95% |
| 错误 INELIGIBLE 误杀 | ≤0.5% |
| 硬判断 Evidence Traceability | 100% |
| 100 Persona 回放 | 无系统性偏差 |
| 未知可申请机会发现率 | ≥30% 出现信号 |
| 周高意图行动率 | ≥15% |
| 100 Source 14 天自动运行 | ≥90% 无日常人工维护 |

这意味着技术验收不是：

> “接口通了。”

而是：

> “系统的判断可以被证明可靠。”

---

# 42. Review Queue

以下事件自动进入人工审核：

```text
官方文档冲突
专业映射不确定
Resolver 置信度不足
关键字段不同解析器冲突
LLM 与 deterministic parser 冲突
用户结构化纠错
重大资格规则首次出现
Gold Sample regression
```

人工不是临时补丁。

> Human Review 本身就是系统正式组件。

---

# 43. 前端架构

## Web / PWA

承担：

- 公开机会观测站；
- 搜索；
- Opportunity Detail；
- 来源；
- 核验时间；
- Revision Timeline；
- 90 秒体检；
- SEO / 分享；
- Add to Home Screen。

## 微信小程序

承担：

- 今日行动；
- 个人机会；
- 计划；
- 提醒；
- 用户反馈；
- 分享。

## Admin / Research Console

承担：

- Source Registry；
- Parser inspection；
- Opportunity merge；
- Rule Review；
- Feedback Review；
- Persona Replay；
- Evaluation；
- Release comparison。

实验室不是另一套后台：

> 它是正式系统的 Research Mode。

这与 Blueprint 的“同一系统、两种运行模式”保持一致。

---

# 44. API 设计

后端采用：

> FastAPI + Pydantic。

公开业务 API 以领域对象而不是页面为中心：

```text
/sources
/opportunities
/opportunities/{id}
/opportunities/{id}/history

/profile
/user-state

/matches
/matches/{id}

/actions
/feedback

/reviews
/evaluations
```

前端、PWA、小程序均共享相同 API Contract。

---

# 45. Repository 结构

建议 monorepo：

```text
deepaha/
│
├── apps/
│   ├── api/
│   ├── web/
│   ├── admin/
│   └── miniprogram/
│
├── backend/
│   ├── source/
│   ├── ingestion/
│   ├── document/
│   ├── opportunity/
│   ├── evidence/
│   ├── rules/
│   ├── eligibility/
│   ├── profile/
│   ├── retrieval/
│   ├── ranking/
│   ├── feedback/
│   ├── evaluation/
│   └── model_gateway/
│
├── workers/
│   ├── fetch/
│   ├── parse/
│   ├── intelligence/
│   └── notification/
│
├── contracts/
│   ├── schemas/
│   └── openapi/
│
├── evaluation/
│   ├── gold/
│   ├── personas/
│   ├── replay/
│   └── reports/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   └── e2e/
│
├── infra/
│
├── docs/
│   ├── architecture/
│   └── adr/
│
└── README.md
```

---

# 46. 开发环境

本地开发尽量简单：

```text
Docker Compose
 │
 ├── PostgreSQL + pgvector
 ├── Valkey
 ├── API
 └── Celery Worker
```

RawArtifact 开发阶段允许本地文件存储。

生产再切：

> S3-compatible managed object storage。

V1 不引入：

- Kubernetes；
- Kafka；
- Elasticsearch；
- Neo4j；
- Airflow；
- 大型 ML Platform。

没有真实需求就不增加基础设施。

---

# 47. 开源项目最终选型表

**截至 2026-08-21 GitHub 尽调结果：**

| 项目 | 质量 | 复用关系 | 决策 |
|---|---|---|---|
| Docling | 极高 | 官方复杂文档解析高度重合 | **A 直接采用** |
| pgvector | 极高 | Opportunity 语义召回高度重合 | **A 直接采用** |
| Playwright Python | 极高 | 动态官方网页采集高度重合 | **A 直接采用** |
| Celery | 极高 | 异步采集/解析/AI任务高度重合 | **A 直接采用** |
| Valkey | 极高 | Broker/Cache 高度重合 | **A 直接采用** |
| PaddleOCR | 极高 | 仅扫描中文文档存在条件复用 | **B 条件采用** |
| LiteLLM | 极高 | Model Gateway 有明显复用 | **B 条件采用** |
| LightGBM | 极高 | 未来 Learning-to-Rank 高度相关 | **B 数据成熟后采用** |
| Unstructured | 高 | 与 Docling 高度重复 | **C Benchmark** |
| Scrapy | 极高 | V1 采集规模不需要 | **C 暂不采用** |
| changedetection.io | 高 | 只有页面变化，缺业务语义 | **C 参考** |
| LangGraph | 极高 | 核心链无需 Agent Orchestration | **C 后置** |
| Microsoft GraphRAG | 极高 | 当前场景过重且进入维护模式 | **C 研究参考** |
| jobsync | 较高 | 产品交互接近，领域范围不同 | **C UX参考** |
| RecruitGPT | 不足 | 概念相关但工程/许可不足 | **D 拒绝** |
| Resume-Job-Matching-System-v1 | 不足 | 工程质量不足 | **D 拒绝** |
| RecBole-PJF | 一般 | 代码维护和许可不足 | **D 拒绝** |

这张表最重要的不是采用了多少开源。

而是：

> **真正进入 DeepAha V1 主链的、有架构意义的外部开源项目只有约 5 个。**

---

# 48. 为什么这比“RecruitGPT + GraphRAG + Agent”路线更好

表面上那条路线 AI 味更浓：

```text
RecruitGPT
+
GraphRAG
+
LangGraph
+
Neo4j
+
Vector DB
+
Multi Agent
```

但实际上会让 DeepAha 成为：

> 一堆 AI 框架之间的胶水代码。

新的方案是：

```text
             DeepAha Domain Core
                    │
        ┌───────────┼───────────┐
        │           │           │
     Evidence     Rules       UserState
        │           │           │
        └──── Opportunity ──────┘
                    │
              Match / Action
                    │
                Feedback
                    │
               Evaluation
```

外部技术只是外围能力。

因此：

> DeepAha 越发展，自己掌握的资产越多，而不是对开源框架依赖越深。

---

# 49. 12 周技术实施顺序

## W1–2：Domain Foundation

完成：

- 数据契约；
- Source Registry；
- RawArtifact；
- Evidence；
- PostgreSQL；
- pgvector；
- Valkey；
- Celery；
- ModelGateway interface。

验收：

> 一份官方网页能够留下不可变原始证据。

---

## W3–4：Document Intelligence

完成：

- HTML Parser；
- XLSX Parser；
- Docling Adapter；
- Evidence Locator；
- 200 Gold Opportunity 输入集。

验收：

> 关键字段解析 ≥97%，高影响字段均有定位。

---

## W5–6：Opportunity + Eligibility

完成：

- Resolver；
- Version；
- Revision；
- Rule DSL；
- Rule Compiler；
- Eligibility 四态；
- 20 母画像 → 100 Persona。

验收：

> INELIGIBLE 误杀逼近 ≤0.5%，Evidence 100%。

---

## W7–8：Matching

完成：

- FTS；
- pgvector recall；
- explainable ranking；
- MatchSnapshot；
- 未来 90 天机会体检。

验收：

> 100 Persona 的 must_find、must_not_reject 回放稳定。

---

## W9–10：Learning Loop

完成：

- ActionEvent；
- FeedbackEvent；
- Review Queue；
- Adjudication；
- EvaluationRun；
- Release Version。

验收：

> 一条真人纠错能够完整进入审核、评估、发布候选链。

---

## W11–12：Product & Scale Validation

完成：

- Web/PWA；
- 小程序行动台；
- Notification；
- 100–300 Source；
- 真实用户 Beta；
- Shadow Replay；
- Go / No-Go Report。

验收：

> 数据可信 + 资格可信 + 真人行动三条同时过 Gate。

---

# 50. Architecture Decision Records

V1.0 锁定以下 ADR。

### ADR-001

**Modular Monolith First**

不做微服务。

### ADR-002

**PostgreSQL First**

不建立 Neo4j / GraphRAG 双数据世界。

### ADR-003

**Rules Before Models**

硬资格不使用机器学习裁决。

### ADR-004

**Evidence Before Explanation**

先存在事实和证据，再生成 AI 解释。

### ADR-005

**Deterministic Parser First**

能结构化解析就不交给 LLM。

### ADR-006

**LLM as Interpreter, not Authority**

LLM 理解自然语言，不掌握最终事实权。

### ADR-007

**No Agent Core**

Agent 不进入核心资格链。

### ADR-008

**No Synthetic Behavioral Truth**

模拟用户不产生商业真值。

### ADR-009

**Feedback Is Evidence, Not Truth**

用户反馈必须经过质检。

### ADR-010

**Open Source Must Earn Its Place**

高质量只是准入条件之一，紧密复用和净收益才决定采用。

---

# 51. DeepAha 真正自有的技术资产

最终系统可以分成两部分。

## 可替代基础能力

```text
LLM
Docling
Playwright
Celery
Valkey
pgvector
Cloud
Frontend Framework
```

全部可以替换。

## DeepAha 不可替代资产

```text
Source Graph
        ×
Opportunity History
        ×
Rule & Evidence
        ×
Youth UserState
        ×
MatchSnapshot
        ×
Feedback / Outcome
        ×
Evaluation Corpus
```

随着系统运行：

```text
更多真实机会
        ↓
更多规则和变化历史
        ↓
更可靠资格判断
        ↓
更多青年真实行动
        ↓
更多反馈和结果
        ↓
更好的排序
        ↓
更高质量机会发现
```

这才是 Opportunity Learning Loop。

---

# 52. 最终技术判断

V1.0 不应该建设成：

> **一个“AI 招聘开源项目”的改造版。**

也不应该建设成：

> **GraphRAG + Agent + Vector DB 的 AI 技术展示项目。**

它应该是一套：

> **以 PostgreSQL 中的 Opportunity Living State 为世界记忆，以 Evidence 和 Rule Engine 为可信判断基础，以 pgvector 为语义召回，以外部 LLM 为语言理解能力，以真人反馈和离线 Evaluation 为持续学习机制的青年机会智能系统。**

因此 V1 的核心技术公式可以写成：

> **DeepAha OIE = Living Opportunity State + Evidence + Deterministic Eligibility + Personal State + Explainable Ranking + Feedback Learning Loop**

而不是：

> LLM + Prompt。

这一架构直接继承 Blueprint 所定义的“可信发现—判断—行动—学习”闭环，并把模型供应商放在可替换的位置，把真正长期积累的 Opportunity History、资格规则、UserState、反馈证据和评估体系掌握在 DeepAha 自己手中。

---

## V1.0 技术基线结论

**现在应该开始开发的，不是 GraphRAG，不是自己的推荐模型，也不是多 Agent。**

第一条工程主线应该严格按照：

```text
Source
→ RawArtifact
→ Document
→ Evidence
→ Opportunity
→ Version
→ Rule
→ Eligibility
→ Retrieval
→ Ranking
→ MatchSnapshot
→ Action
→ Feedback
→ Evaluation
→ Release
```

推进。

只要这一条链稳定成立，DeepAha 就已经拥有了第一版真正的 **Opportunity Intelligence Engine**。

后面的知识图谱、Learning-to-Rank、模型微调、原生 App、B 端人才智能服务，都应该是在这条主链被真实数据证明之后，再逐层增加，而不是现在预装复杂度。