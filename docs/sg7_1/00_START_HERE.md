# SG7.1 Start Here

SG7.1 是 3.7.0-rc1 / SG7 的可信度修正版，不新增第二套产品。

只解决四件事：

1. 100 个数字分身组合覆盖改为 V2；
2. Gold Benchmark 与正式推荐候选过滤完全对齐；
3. 增加与被测代码分离的确定性标准答案 Oracle；
4. 从已有 SG7 V1 实验数据安全升级到 Lab Logic V2。

先读：

- `01_CORE_CORRECTIONS.md`
- `02_INDEPENDENT_GOLD_ORACLE.md`
- `03_VALIDATION.md`
- `04_LOCAL_REPRODUCTION.md`

绝对边界：工程标准答案不是独立人工 Gold，Synthetic Twin 不是 Founding User，实验结果不能回写正式 Opportunity / VerifiedFact / Rule / Eligibility / Ranking / Review Decision。
