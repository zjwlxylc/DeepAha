# SG7.1 核心修正设计

## 1. V1 暴露的问题

### 1.1 数字分身组合相关

SG7 V1 同时使用 `i % 4` 生成学历与毕业年份，导致两列人为绑定。数量虽为 100，但若关键维度不能充分交叉，压力测试会出现“看起来样本很多，实际组合缺失”。

SG7.1 将毕业年份改成独立的分组周期：

- 学历仍按 4 人周期；
- 毕业年份按每 4 人切换；
- 与专业、城市、机会类型等继续交叉；
- 通过固定 profile hash 保证 V2 可重复。

### 1.2 Gold Benchmark 绕过正式召回 Gate

正式“我的机会星图”在明确选择机会类型时会先按类型硬过滤；`STRICT` 地区模式也会先过滤明确异地机会。SG7 V1 的 Benchmark 曾直接把所有 Gold Opportunity 送给所有 Twin 做 Value，这会把正式产品根本不会展示的 Pair 误计为 FEATURE。

SG7.1 的顺序固定为：

```text
Gold Opportunity × Twin
        ↓
显式 Opportunity Type Gate
        ↓
STRICT Region Gate
        ↓
SG4 Eligibility
        ↓
SG5 Value / Priority
        ↓
FEATURE / EXPLORE / HOLD
```

被前置 Gate 排除的 Pair 统一记录：

- `priority_band = NOT_RECOMMENDED`
- `recommendation_class = HOLD`
- `detail.retrieval_excluded_reason` 说明原因。

### 1.3 不能再“系统自己给自己判卷”

SG7.1 新增两套工程 Oracle 测试。Oracle 只根据预先冻结的 fixture 规则和 Twin 字段生成标准答案，不导入或调用生产 Eligibility/Value 函数。

这只证明：

> 对明确、确定性、可机械判定的题目，正式程序答案是否与独立规则标准答案一致。

它不能证明：

> 一个真实青年主观上是否觉得这个机会值得行动。

后者仍必须由 independent human Gold + Founding User 行为验证。

## 2. SG7.1 升级策略

实验层版本升为 V2。

从 3.7.0 启动：

1. 先完整备份 SQLite + Object Store；
2. 保留所有 V1 Twin / Pair Truth / Run；
3. 只把 V1 Twin 标记为 inactive；
4. `opportunity_lab_schema_version` → 2；
5. 用户/维护者重新生成 V2 100 Twins；
6. V1 历史仍可审计，不被覆盖。

生产事实与用户主产品数据不变化。
