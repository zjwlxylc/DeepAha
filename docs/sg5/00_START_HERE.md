# SG5｜个人机会智能（Should I? / Why now?）

版本：`3.5.0-rc1`。基线：用户已人工验收通过的 SG1–SG4。

SG5 的目标不是增加更多机会，也不是给用户显示一个看起来聪明的“匹配度”。它把 SG4 已经建立的 **Can I?** 资格边界放在前面，再回答：

1. **Should I?** —— 即使我能参加/尚不能完全判断，这个机会是否值得我优先关注？
2. **Why now?** —— 是否存在可靠的行动窗口，为什么现在要看？
3. **Why me?** —— 哪些画像信息与这个机会发生了可解释关联？

主链：

```text
CURRENT / UPDATE_PENDING Actionable Target
        ↓
有界候选召回（SQL + 轻量本地特征）
        ↓
SG4 Eligibility
        ↓
INELIGIBLE 硬过滤
        ↓
Value Features / Priority / Urgency
        ↓
Top-N diversified star map
        ↓
Why for you / Why now / Risks
```

## 本轮明确不做

- 不做 `User × All Opportunities × LLM`；
- 不调用 WMA/外部 LLM 计算个人排序；
- 不显示“92% 匹配度”“成功率”“录取概率”；
- 不训练排序模型；
- 不把画像兴趣转成资格事实；
- 不进入 SG6 的持续监测/反馈学习闭环；
- 不新增支付、套餐或商业化。

## 先读

1. `01_VALUE_PRIORITY_SPEC.md`
2. `SG5_ACCEPTANCE.md`
3. `SG5_LOCAL_REPRODUCTION.md`
4. `../development/SG5_PERSONAL_VALUE_DELIVERY.md`
5. `../../evidence/sg5/REAL_WMA_DATA_ANALYSIS.md`
