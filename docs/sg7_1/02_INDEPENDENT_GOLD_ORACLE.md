# SG7.1 独立标准答案 Oracle

## 一、为什么要有 Oracle

Digital Twin 是测试输入，不是真人裁判。不能采用：

```text
AI扮演用户 → 程序推荐 → AI再评价程序
```

因此 SG7.1 工程自测采用：

```text
预先定义规则题
      ↓
独立确定性 Oracle 生成标准答案
      ↓ 先冻结
正式 SG7.1 Eligibility / Recommendation 答题
      ↓
逐 Pair 比较
```

## 二、Oracle 的隔离要求

Oracle 测试代码不得：

- 调用 WMA；
- 调用外部 LLM；
- 调用 `eligibility.evaluate()` 生成标准答案；
- 调用 `value.assess()` 生成标准答案；
- 读取被测程序最终答案后再修改标准答案。

## 三、资格标准答案

6 类固定题 × 100 V2 Twins = 600 Pair：

| 题型 | 标准答案逻辑 |
|---|---|
| 本科及以上 | education rank ≥ 本科 → ELIGIBLE，否则 INELIGIBLE |
| 硕士及以上 | education rank ≥ 硕士 → ELIGIBLE，否则 INELIGIBLE |
| 本科及以上 + 2027届 | 两条件同时满足 → ELIGIBLE，否则 INELIGIBLE |
| 已过截止期 | INELIGIBLE |
| 专业代码必需但 Twin 无 major_code | UNCERTAIN |
| 学历条件含“高级职称可放宽”例外 | 未验证例外分支前保持 UNCERTAIN |

实际分布：

- BACHELOR_MIN：75 ELIGIBLE / 25 INELIGIBLE；
- MASTER_MIN：25 ELIGIBLE / 75 INELIGIBLE；
- BACHELOR_2027：21 ELIGIBLE / 79 INELIGIBLE；
- EXPIRED：100 INELIGIBLE；
- MISSING_MAJOR_CODE：100 UNCERTAIN；
- EXCEPTION_LANGUAGE：100 UNCERTAIN。

最终：**600/600**。

## 四、推荐标准答案

20 个未来、无硬资格冲突、固定类型/地区的通用机会 × 100 V2 Twins = 2000 Pair。

独立 Oracle 只判正式候选硬 Gate：

- 用户有显式机会类型偏好且类型不匹配 → HOLD；
- `STRICT` 地区模式且明确地区不匹配 → HOLD；
- 其余本 fixture 由于是安全、未来、通用机会且类型命中 → FEATURE。

实际标准答案：

- FEATURE：371；
- HOLD：1629。

最终混淆矩阵：

- FEATURE → FEATURE：371；
- HOLD → HOLD：1629；
- mismatch：0。

最终：**2000/2000**。

## 五、不能误解为真人验证

这些 Pair 的 `truth_origin` 是 `ENGINEERING_FIXTURE`。

因此：

- `real_gold_pairs = 0`；
- 不能宣传“真人准确率 100%”；
- 不能替代独立人工标注；
- 不能替代真实用户“以前是否知道 / 是否觉得有用 / 是否行动 / 最终结果”。
