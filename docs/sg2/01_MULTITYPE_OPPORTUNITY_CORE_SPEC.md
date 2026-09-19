# SG2 多类型 Opportunity Core 规格

## 1. 目标

DeepAha 的核心对象是 **Opportunity**，不是 Job。SG2 将 SG1 已建立的：

`Opportunity Root → Unit → Catalog Target`

推广到多种青年机会，而不为每一种机会重新建一套数据模型。

## 2. 共同模型

### Opportunity Root

代表一次官方公告、计划、赛事、政策、项目或招生说明。继续承担：

- 一次整体审核；
- 原件与证据；
- 来源与版本；
- 父级共同条件；
- 历史追溯。

### Unit

表示 Root 内有真实业务意义的层级。稳定 `kind`：

- `GROUP`：只表达范围/组织/分组，不默认进入用户总览；
- `POSITION`：岗位或岗位型分项；
- `TRACK`：赛道、研究方向、项目方向；
- `PROGRAM_TIER`：组别、档次、项目类别；
- `REGION_VARIANT`：地区/赛区/属地变体；
- `DEFAULT_SINGLETON`：没有进一步可行动子项时的单一机会。

### Catalog Target

真正允许用户独立：

- 浏览；
- 收藏；
- 提醒；
- 反馈；
- 后续做 Eligibility/Value/Priority。

当一个 actionable Unit 下面还有更具体的 actionable 后代时，只发布**最具体的行动前沿**，避免“赛道 + 赛道下组别”重复出卡。

## 3. 类型语义

| Opportunity 类型 | 常见 Root | 常见 Unit | 用户卡片基本单位 |
|---|---|---|---|
| 招聘 / 校招 | 招聘公告 | GROUP → POSITION | POSITION |
| 实习 | 实习计划/公告 | GROUP → POSITION | POSITION |
| 竞赛 | 赛事 | TRACK → PROGRAM_TIER | 最具体赛道/组别 |
| 科研 | 科研计划 | GROUP → TRACK | TRACK / 研究岗位 |
| 奖学金 | 奖助计划 | PROGRAM_TIER | 资助档次 |
| 人才政策/补贴 | 政策 | REGION_VARIANT / PROGRAM_TIER | 地区政策/支持档次 |
| 推免/保研/夏令营 | 项目/招生说明 | TRACK / PROGRAM_TIER | 项目方向/类别 |
| 成长实践 | 实践计划 | GROUP / TRACK / DEFAULT_SINGLETON | 最具体可行动分项 |

## 4. Presentation 与事实分离

类型模板只控制这些词：

- “岗位 / 赛道 / 研究方向 / 资助档次 / 地区政策 / 项目类别”；
- “公告共同条件 / 赛事共同规则 / 政策共同条件”等标题；
- “报名时间 / 申请时间 / 受理时间”；
- “查看报名方式 / 查看参赛入口 / 查看办理方式”。

模板**不得**：

- 修改事实值；
- 自动补齐未知字段；
- 生成资格规则；
- 把“滚动受理”转成固定日期；
- 把父级条件无证据复制成子级确定事实。

实现入口：`backend/src/deepaha/product/opportunity_core.py`。

## 5. Scope 规则

- Root `fields` → `common_fields`；
- 父级 Unit 字段 → `ancestor_fields`；
- 当前行动 Unit 字段 → `fields`；
- `scope_labels` 保存用户可理解的父路径；
- 非招聘类型的 GROUP 默认**不是 issuer**；发布方仍来自 Root；
- 招聘/实习岗位可以使用最近 GROUP 作为具体单位名。

## 6. 时间规则

SG2 延续 SG1 的安全时间策略：

- 只有 exact date 且引用定位支持同一日期，才允许作为精确行动日期；
- 子项有可靠日期时可以覆盖 Root 日期；
- 相互冲突时不选一个“看起来更像”的日期；
- “常年受理 / 滚动受理 / 招满即止 / 待公布”保留原文，不制造倒计时。

SG3 才负责完整的版本、延期、更正、撤回和当前性。

## 7. 无链接机会

`application_url` 不是总览准入条件。线下办理、邮件申请或只提供官方说明页的机会仍然可以展示。

## 8. Unknown fields

无法进入标准字段字典的新标签仍然：

- 保留原标签；
- 保留完整原文；
- 保留 evidence/notes；
- 可通过文本搜索找到；
- 不因为“不认识字段”而阻断整份 Opportunity。

## 9. SG2 明确不做

- Eligibility（SG4）；
- 个性价值/排序（SG5）；
- 生命周期/更正撤回（SG3）；
- 支付/订阅；
- 新机构后台；
- 全国扩源；
- 恢复逐字段审核。
