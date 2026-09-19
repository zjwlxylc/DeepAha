# SG7 Opportunity Lab 设计

版本：DeepAha 3.7.0-rc1

## 1. SG7 为什么现在做

SG6.2 已经把正式主链推进到：真实机会 → 一次整体审核 → 资格证据编译 → Eligibility → Value/Priority → 行动闭环。SG7 不再继续堆“正式事实治理”，而是回答下一层核心问题：

> **DeepAha 的资格判断和机会排序，面对不同青年画像，到底是否安全、是否有价值？**

因此 SG7 是同一个 DeepAha 产品中的研发/验证模式，不是第二个产品，也不是新的正式事实审批系统。

## 2. 四类核心对象

### 2.1 Synthetic Youth Digital Twin

用于覆盖不同教育、专业、城市、目标、技能和约束组合。SG7 默认可确定性生成恰好 100 个 Twin：

- 不使用真人姓名；
- 不复制真实用户数据库；
- profile JSON + hash + version 锁定；
- 重复生成幂等；
- 只用于实验，不进入用户账号体系。

### 2.2 Lab Gold Case

从当前已发布 CatalogTarget 制作不可变实验快照。它回答：

> “本次实验使用的是哪一个生产机会版本？”

它**不**回答：

> “所有用户对这个机会都应该是 ELIGIBLE / INELIGIBLE。”

因此 Gold Case 与资格真值严格分离。

### 2.3 Pair Truth

资格和推荐都属于“人 × 机会”的关系，因此真值必须落在：

> **Gold Opportunity × Digital Twin**

Pair Truth 可以分别提供：

- `expected_eligibility`：ELIGIBLE / LIKELY_ELIGIBLE / UNCERTAIN / INELIGIBLE；
- `expected_recommendation`：FEATURE / EXPLORE / HOLD。

两者可以单独存在。系统禁止因为标了“推荐给他”就顺便猜一个资格真值。

### 2.4 Founding User Experiment

真人用户只有显式同意后才进入共创实验：

- 加入前不记录实验曝光；
- 可以随时退出；
- 退出不影响收藏、申请和正式产品使用；
- operator 只看到聚合指标，不展示完整画像和自由文本隐私内容；
- 用户隐私导出和清除会同步覆盖实验记录。

## 3. 两类 Benchmark

### CATALOG_SAFETY

目的：验证当前正式 Catalog 对一批数字分身是否出现明显不安全推荐。

它不需要人工 Gold，主要看：

- INELIGIBLE 是否仍被高推荐；
- HIGH qualification risk 是否被错误提升到 headline；
- 正式 SG4/SG5 安全门是否回归。

### GOLD_BENCHMARK

目的：只在有明确 Pair Truth 的样本上测准确率。

规则：

- 无真值 → 不计准确率；
- operator/engineering 标注与 independent human gold 分开计数；
- `INDEPENDENT_HUMAN_GOLD` 必须有 `attestation_ref`；
- 资格准确率和推荐准确率分别计算；
- 实验结果绝不回写生产 Eligibility/Ranking。

## 4. 生产权威不变

SG7 数据域只拥有：

- Twin；
- Lab Case；
- Pair Truth；
- Lab Run / Result；
- Founding Enrollment / Exposure。

它没有权限批准或改变：

- Source；
- WMA Candidate Facts；
- VerifiedFact；
- Rule；
- Overview Decision / Publication；
- 正式 Eligibility；
- 正式 Value / Priority。

## 5. 不做的事情

SG7 明确不做：

- 训练自己的基础大模型；
- 把数字分身当真人反馈；
- 把 operator 标注冒充独立人工 Gold；
- 自动改规则/权重；
- 支付/订阅；
- 完整 A/B 实验编排平台；
- 对 WMA 做新一轮 Runtime 重构；
- 进入 SG8。
