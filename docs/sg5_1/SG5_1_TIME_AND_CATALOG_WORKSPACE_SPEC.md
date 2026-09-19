# SG5.1 时间语义与收录管理工作台设计

## 目标

在不进入 SG6 的前提下，修复 SG5 已暴露的两个产品缺口：

1. WMA 已读出的报名/申请/提交等时间信息，在证据安全边界内转化为可计算的 Milestone；
2. 将收录管理从“具体机会平铺大表”重构为“父公告/根机会为管理单元、具体机会为精确操作单元”的工作台。

## 一、Milestone 时间语义轨

### 1. 输入

从 CatalogTarget 的 own / ancestor / common 三个 scope 读取字段，不修改 WMA 原始输出。

识别的首版事件：
- APPLICATION_OPEN
- APPLICATION_DEADLINE
- SUBMISSION_DEADLINE
- REVIEW_WINDOW
- PAYMENT_WINDOW
- ADMISSION_TICKET_WINDOW
- EXAM_DATE
- INTERVIEW_DATE
- RESULT_DATE
- ROLLING_APPLICATION
- OTHER_TIME

### 2. 安全提升条件

可计算 Milestone 必须同时满足：
- 字段状态为 CONFIRMED / KNOWN；
- 事件语义能确定性识别；
- 日期/时间能确定性解析；
- 至少一个 Evidence 经 SG4 EvidenceResolver 在不可覆盖原件中重新定位；
- 已定位 Evidence 的引文实际包含/支持被规范化的日期或时刻，不能只凭 located=true 接受模型给出的另一日期；
- 同一作用域同一事件不存在互相冲突的已定位值；
- SG3 未将该字段标为更新待收录。

任何一项不满足：保留原文，不生成精确倒计时/提醒。

### 3. 精度

- MINUTE：精确到时分；
- DAY：精确到日期；
- MONTH：仅月份，不可生成精确截止倒计时；
- RANGE：明确起止；
- ROLLING：滚动/常年/招满即止；
- UNRESOLVED：存在时间语义但不能安全规范化。

### 4. 当前行动截止

CatalogTarget.deadline 仅从当前 Target 的可计算 `APPLICATION_DEADLINE` 产生。
如果只有 `报名时间` 范围，则范围结束值可作为 APPLICATION_DEADLINE，但必须由已定位原文支持。
竞赛的作品提交截止单独保存为 SUBMISSION_DEADLINE，不默认替代报名截止。

### 5. 时间质量状态

- READY：有可计算的主要行动截止；
- ROLLING：明确滚动/常年受理；
- PARTIAL：存在已定位时间节点，但主要行动截止仍不确定；
- CONFLICT：存在同事件的已定位冲突；
- PENDING_UPDATE：SG3 更新影响时间字段；
- UNKNOWN：没有可安全使用的时间节点。

## 二、收录管理工作台

### 1. 默认管理单元

默认按 Opportunity Root / 父公告分组，不按具体 Target 平铺。

每组显示：
- 父公告标题、发布方、类型；
- 当前具体机会数；
- CURRENT / UPDATE_PENDING 数；
- READY / ROLLING / PARTIAL / CONFLICT / UNKNOWN 数；
- 最早安全截止；
- 收录时间与最近版本时间；
- 需要处理的风险摘要。

### 2. 顶部指标

只保留可操作指标：
- 当前具体机会；
- 父公告 / 根机会；
- 更新待处理；
- 时间待确认（PARTIAL + CONFLICT + UNKNOWN + PENDING_UPDATE）；
- 已过截止（安全 deadline 已经早于当前日期）。

### 3. 两种视图

- 按公告：默认，用于运营管理和问题定位；
- 按具体机会：次级，用于搜索、精确撤回和查看单个 Target。

### 4. 筛选

统一支持：
- 搜索；
- 类型；
- 状态；
- 时间质量。

### 5. 精确操作

父公告视图不提供“一键撤回整组”默认动作。
具体 Target 仍保留现有精确撤回；公告级撤回只走已有明确 Root withdrawal 语义。

## 三、兼容与不做

- 不新增第二套事实库；
- 不修改 WMA Prompt；
- 不让人工逐字段批准日期；
- 不让未定位字符串直接变成倒计时；
- 不进入 SG6 的提醒学习/行为反馈扩展；
- 保留 SG1-SG5 已验收的 Root/Unit/Target、Currentness、Eligibility、Value 语义。
