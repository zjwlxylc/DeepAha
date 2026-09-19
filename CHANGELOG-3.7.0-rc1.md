# DeepAha 3.7.0-rc1 / SG7

SG7 将 SG6.2 已验收的正式产品主链扩展为 **Opportunity Lab（机会实验室）**：在不改写正式机会事实、审核结论、资格规则和 WMA 数据生产权威的前提下，增加数字分身、Gold/Pair Truth、推荐安全基准和 Founding User 共创实验能力。

## 新增

- 100 个版本化、可复现的 Synthetic Youth Digital Twins；
- 隔离的 Lab Gold Case，不回写生产 Opportunity / VerifiedFact / Rule；
- `Opportunity × Digital Twin` Pair Truth：资格真值与推荐真值分开标注；
- `CATALOG_SAFETY` 与 `GOLD_BENCHMARK` 两类实验运行；
- 同时验证 `Can I?` 与 `Should I?`，不再把推荐质量等同于资格准确率；
- Founding User 自愿加入/退出、曝光记录、聚合反馈与行动指标；
- 用户隐私导出/清除同步覆盖 SG7 实验数据；
- operator 机会实验室页面、普通用户机会共创实验页面；
- backup-first `upgrade-sg7`；Windows 启动器自动在 SG6.2 后执行；
- SG7 设计、实验协议、验证与本地复现文档。

## 继续保持的硬边界

- SG6.2 人工验收结果作为基线，不重写 SG1–SG6.2；
- reviewer 仍只做一次整体通过/不通过，不恢复逐字段审核；
- Lab Gold 不批准生产事实；Pair Truth 不修改生产 Eligibility/Ranking；
- Synthetic Twin 不冒充真实用户或真实市场证据；
- `INDEPENDENT_HUMAN_GOLD` 必须有人工佐证引用；
- Gold Benchmark 没有对应 Pair Truth 时不计算“准确率”，禁止假绿；
- Founding User 必须显式同意，可随时退出；退出不影响主产品正常使用；
- SG7 不把用户完整画像发送给 WMA，不自动训练外部模型；
- SG7 基准运行不调用 WMA/LLM；
- 不进入支付、商业化、自动模型训练或 SG8。

## 工程验证

- `backend/tests/product`：26 个测试文件，216 tests，逐文件隔离执行，全部 `RC=0`；
- Python `compileall`：PASS；
- 前端语法 + product/SG5/SG5.1/SG6/SG6.1/SG7 契约：PASS；
- 真实 HTTP Smoke：3.7.0-rc1 启动、Cookie+CSRF 登录、100 Twin、Gold Benchmark、Founding User join/leave：PASS；
- 最终 HTTP Gold Smoke：1 个锁定机会 × 100 Twins = 100 pairs，`unsafe_recommendations=0`，`llm_used=false`，`production_mutated=false`；
- WMA Live Binding：本运行容器无法安装项目锁定 SDK（外网/DNS受限），未冒充执行；SG7 本身不依赖 WMA 调用，现有 Direct WMA 产品边界未改；
- 浏览器视觉自动化：当前容器 Chrome 对 localhost 被管理策略阻止，未冒充视觉通过；由用户 Windows 本地进行最终人工 UI 验收。
