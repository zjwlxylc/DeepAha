# SG3 版本、变化与当前性规格

## 1. 核心问题

SG1/SG2 已经把“公告”拆成具体可行动 Opportunity Target。SG3 解决的是：**这些 Target 会变化。**

官方可能发布更正、延期、撤回、替换附件；WMA 也可能在一次后续调查中只返回部分子项。系统必须知道“什么真的变了、影响谁、现在还能不能用于提醒”，而不是把整份公告一起作废。

## 2. 不可退让语义

### 2.1 缺失不等于撤回

新版返回没有出现某个旧 Target，只能得到 `MISSING_PENDING`。没有明确官方撤回或审核员主动撤回，不得自动删除。

### 2.2 局部变化只影响局部

A01 延期，只能让 A01 进入 `UPDATE_PENDING`。同公告 A02 若内容/证据未变，继续 `CURRENT`。

父级共同条件变化，才可以影响其所有后代。

### 2.3 旧值可以保留历史，但不能继续驱动错误行动

新更正尚未整体收录前，旧版本仍保存在数据库中用于追溯；如果已知某个截止字段存在新变化，该字段在用户当前视图中不能继续作为有效截止提醒依据。

拒绝新版本也不能自动“复活”已知可能过时的旧提醒。

### 2.4 明确撤回需要明确依据

只有以下情况产生正式 WITHDRAWN：

- 已整体通过的新返回明确标记该 Root/Unit 撤回、取消；
- 有权限的审核/运营人员执行明确的“撤回具体机会”动作。

### 2.5 历史不覆盖

每次已收录更正产生新的 CatalogTarget 版本。旧版本变为 SUPERSEDED/WITHDRAWN，但仍可查询。比较接口必须能展示 before/after。

## 3. 状态

当前 Target 主要使用：

- `CURRENT`：当前可用；
- `UPDATE_PENDING`：已知有变化、缺失或撤回候选，等待整体收录/复查；
- `SUPERSEDED`：被更新版本替代的历史；
- `WITHDRAWN`：明确撤回的历史/当前终止状态。

候选变化类型至少包括：

- `UPDATED`；
- `DEADLINE_CHANGED`（语义上属于更新时间变化，具体 diff 可同时包含字段/证据）；
- `EVIDENCE_REPLACED`；
- `MISSING_PENDING`；
- `WITHDRAWAL_PENDING`；
- `ADDED_PENDING`。

## 4. 数据流

```text
当前已收录 Revision/Target
        +
新的 WMA 返回
        ↓
按 SG1 稳定 Unit identity 投影
        ↓
Currentness Comparator
        ↓
Target-scoped Diff
        ↓
只标记受影响 Target UPDATE_PENDING
        ↓
整体审核 APPROVE / REJECT
        ↓
APPROVE: 新版本 CURRENT / 明确撤回 WITHDRAWN
REJECT: 保留 pending 风险，不恢复过时提醒
        ↓
History / Compare / Recheck
```

## 5. 当前性比较范围

比较：

- title/code/region/application URL 等目标级元数据；
- deadline；
- own/group/common fields；
- Evidence 引用；
- 被替换 Artifact；
- lifecycle marker；
- target 是否新增/本轮缺失。

不以文字相似度擅自把两个弱身份 Target 合并为同一项。

## 6. Reminder/Action 规则

- 只有受影响 deadline 的 Target 取消旧 deadline notice；
- 兄弟 Target 的提醒保持；
- UPDATE_PENDING 但 deadline 未受影响时，不必抹掉其他安全值；
- 明确撤回后当前行动目标退出，但历史和用户历史反馈保留。

## 7. 定向复查

SG3 不新建第二个 Agent 系统。复用现有 Direct WMA `RECHECK` Task：

- 输入固定 target public id；
- 固定受影响字段；
- 只追查该 Target 直接相关的更正/附件/延期/撤回；
- 不扩展到兄弟 Target；
- 明确写入“本轮未看到不得据此判撤回”。

## 8. 明确不做

SG3 不实现：

- Eligibility / Rule Engine 新能力；
- 个性化排序；
- 自动决定用户是否符合；
- 支付；
- 外部短信/微信通知；
- Source Scout 扩源；
- 重新设计 WMA Prompt。
