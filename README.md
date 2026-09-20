# 本次候选：experience-84353c7-20260920

基线 `84353c7`。完整体验改善源码交付；**未部署、未推送、未做真实 WMA / PostgreSQL / 真人验收**。
先读 `docs/experience/README.md`、`TEST_REPORT.md`、`RUN_AND_UPGRADE.md`、`RELEASE_AND_ROLLBACK.md`（均在 docs/experience）。
此候选新增五张表，必须先备份后执行 `upgrade-experience`；旧 Worker 不可直接在新任务队列上回退运行。以下保留 SG8-A 历史记录，不代表本候选当前状态。

---

# DeepAha 机会星图 · 3.8.0-rc1（SG8-A）

**基线：3.7.2-rc1 / SG7.2。SG8-A 不改变机会生产、整体审核、Eligibility、Value/Priority、Gold Benchmark 或首页产品逻辑，只把已通过本地工程验证的产品升级为可长期 staging / production 发布、备份、迁移与回退的 Public Beta 底座。**

## SG8-A 新增什么

- 本地 SQLite 正式数据可通过已校验 backup 迁移到**空 PostgreSQL**；
- 迁移逐表做 canonical SHA256，原件逐文件 SHA256；本地 session 撤销，WMA 密钥不迁移；
- `deploy-check`：公网发布前只读检查 production mode / PostgreSQL / schema / active account / data dir / WMA配置；
- `staging.deepaha.com` 与 `www.deepaha.com` 双环境模板；
- `/opt/deepaha/releases/<version>` + `staging-current/production-current` 版本发布；
- systemd API/Worker 模板、Nginx TLS/限流/Basic Auth 模板；
- PostgreSQL + objects 静止窗口备份、备份校验、空目标恢复；
- 自动 HTTP Smoke；同 DB generation 才允许自动 code rollback；
- 可选 Docker PostgreSQL 本地同构模拟；
- Windows `scripts/export-sg8a-portable.cmd` 导出服务器迁移包。

## SG8-A 推荐发布顺序

```text
本地 SG8-A + 现有 deepaha-data
  ↓ export-sg8a-portable
PostgreSQL staging
  ↓ staging.deepaha.com
人工验收
  ↓ production backup + deploy
www.deepaha.com Public Beta
```

**不要直接在服务器修改源码。**以后版本统一走：本地开发 → tests → staging → 人工确认 → production。

## SG8-A 入口

- `docs/sg8_a/00_START_HERE.md`
- `docs/sg8_a/02_DATA_MIGRATION.md`
- `docs/sg8_a/03_SERVER_DEPLOYMENT.md`
- `docs/sg8_a/04_RELEASE_ROLLBACK.md`
- `docs/sg8_a/05_VALIDATION.md`
- `docs/sg8_a/06_CODEX_DEPLOY_TASK.md`
- `CHANGELOG-3.8.0-rc1.md`

## SG7.2 / SG7.1 业务能力继续完整保留

## SG7 新增什么

### 1. 机会实验室

operator 工作台新增 `机会实验室`：

- 生成固定版本的 100 个 Synthetic Youth Digital Twins；
- 将当前已发布机会制作成隔离 Lab Case；
- 为 `机会 × 数字分身` 分别标注资格真值和推荐真值；
- 运行 Catalog Safety / Gold Benchmark；
- 查看 unsafe recommendation、资格准确率、推荐准确率与真值来源；
- 查看 Founding User 聚合反馈与行动指标。

### 2. 推荐质量不再等同于资格正确

SG7 明确拆开：

- **Eligibility / Can I?**：我有没有资格；
- **Recommendation / Should I?**：即使能参加，值不值得重点推荐。

因此 Pair Truth 可以单独标注：

- `expected_eligibility`；
- `expected_recommendation = FEATURE / EXPLORE / HOLD`。

不能因为“值得推荐”就猜一个资格真值，也不能因为“符合资格”就自动认为值得 headline 推荐。

### 3. Founding User 共创实验

普通用户在 `我的 → 机会共创实验` 中：

- 默认不参加；
- 必须主动加入；
- 可以随时退出；
- 退出不影响收藏/准备/申请等正式产品功能；
- 自己的实验状态和曝光进入隐私导出/清除；
- operator 只看聚合指标。

## 生产权威完全不变

SG7 Lab **不能**：

- 批准 Source；
- 修改 WMA Candidate Facts；
- 批准 VerifiedFact / Rule；
- 改写 Overview Decision / Publication；
- 改写正式 Eligibility；
- 自动改 SG5 排序权重；
- 训练外部大模型。

SG6.2 的硬边界继续成立：

- reviewer 仍只对一份 WMA 返回做一次整体通过/不通过；
- 不恢复逐字段人工审核；
- WMA 不能自我批准正式事实；
- `INELIGIBLE` 仍必须由当前正式内容 + 已定位 Evidence + 确定性硬条件冲突产生；
- Evidence 不足继续 `UNCERTAIN`；
- HIGH qualification risk 不得进入 headline。

## 当前主链 + SG7 实验层

```text
Scout / Approved Source
  ↓
Direct WMA + Immutable Artifact / Candidate Facts / Evidence
  ↓
一次整体审核
  ↓
Root → Unit → Actionable Target
  ↓
SG3 Currentness
  ↓
SG6.2 Qualification Evidence Compiler
  ↓
SG4 Eligibility (Can I?)
  ↓
SG5 Value / Priority (Should I? / Why now?)
  ↓
SG5.1 Evidence-backed Milestones
  ↓
SG6 Save → Prepare → Apply → Wait → Complete → Outcome

                 │ 只读生产结果
                 ▼
SG7 Opportunity Lab
  ├─ 100 Synthetic Twins
  ├─ Lab Gold Cases
  ├─ Opportunity × Twin Pair Truths
  ├─ Safety / Gold Benchmark
  └─ Founding User consent + aggregate feedback
```


## SG7.2 公网首页与品牌收口

SG7.2 不改变 SG7.1 的业务算法，而是把已经确认的公网产品化表达迁入真实产品：

- `/`：五段式产品首页（首屏 → 找到 → 判断 → 行动 → 品牌收束）；
- `/about`：正式“关于我们”；
- 使用用户提供的新 DeepAha Logo 替换共用品牌标志与 favicon；
- 首页 CTA 直连真实 `机会总览 / 我的机会星图`；
- 保留证据、不确定性和资格纪律，不复制原型中的伪精确 `94%` 匹配分；
- 桌面 / 手机使用同一真实 SPA，不另建演示站。

SG7.2 **无新增数据库迁移、无 WMA 变更、无 Eligibility / Value / Gold Benchmark 业务修改**。

## SG7.1 核心修正

- Synthetic Twin 升级为 V2，修正学历/毕业年份组合相关；
- Gold Benchmark 先走正式类型/STRICT地区候选 Gate，再进入 Eligibility/Value；
- 新增完全独立于生产评估函数的确定性 Gold Oracle：资格 600/600、推荐 2000/2000；
- 工程 Oracle 永远标记 `ENGINEERING_FIXTURE`，不冒充 `INDEPENDENT_HUMAN_GOLD`；
- SG7 V1 实验历史保留，V1 Twin 退出 active 工作集。

## 升级

沿用原数据目录：

`C:\Users\LENOVO\deepaha-data`

首次启动升级链：

```text
upgrade
→ upgrade-sg1
→ upgrade-sg5-1
→ upgrade-sg6
→ upgrade-sg6-2
→ upgrade-sg7
→ serve / worker
```

`upgrade-sg7` 在 SG7.1 负责隔离实验层 V2 检查/升级：

- SQLite 本地模式 backup-first；
- 不重新调用 WMA；
- 不改 WMA 原件；
- 不改已审核 Opportunity / Unit / Publication；
- 不改正式 Eligibility / Ranking / Action；
- 从 3.7.0 升级时保留 V1 实验历史，只让 V1 Twin 退出 active 工作集；
- 第二次执行幂等。

## SG7.2 历史自测结果（继续作为业务回归基线）

SG7.2 当时最终代码：

- 29 个 `backend/tests/product` 文件；
- 221 tests；
- failed files = 0；
- 每个文件独立 pytest 进程真实 `RC=0`；
- Python compileall PASS；
- product / SG5 / SG5.1 / SG6 / SG6.1 / SG7 前端契约 PASS；
- SG7.1 独立资格 Oracle：600/600；
- SG7.1 独立推荐 Oracle：2000/2000；
- 真实 HTTP Smoke PASS；
- HTTP Gold Smoke：1 case × 100 V2 twins = 100 pairs，unsafe=0，`llm_used=false`，`production_mutated=false`。

SG7.1 不修改 Direct WMA 调用协议，也不需要 WMA 参与 Gold Oracle，因此本轮没有额外发起 WMA 调查调用。当前容器未完成自动浏览器视觉验收，最终视觉/操作仍以 Windows 本地人工确认。

## 主要文档

- `docs/sg7_2/00_START_HERE.md`
- `docs/sg7_2/01_PUBLIC_HOME_ABOUT_DESIGN.md`
- `docs/sg7_2/02_VALIDATION.md`
- `docs/sg7_2/03_LOCAL_REPRODUCTION.md`
- `CHANGELOG-3.7.2-rc1.md`

- `docs/sg7_1/00_START_HERE.md`
- `docs/sg7_1/01_CORE_CORRECTIONS.md`
- `docs/sg7_1/02_INDEPENDENT_GOLD_ORACLE.md`
- `docs/sg7_1/03_VALIDATION.md`
- `docs/sg7_1/04_LOCAL_REPRODUCTION.md`
- `docs/sg7/05_EXPERIMENT_PROTOCOL.md`（SG7实验原则，继续有效）
- `CHANGELOG-3.7.1-rc1.md`
- `DeepAha_SG7_1_本地复现说明.md`
- `DeepAha_SG7_1_自测报告.md`

本包状态：**SG8-A 工程自测通过 / 服务器 staging 实机部署候选**。真实 PostgreSQL、Nginx、systemd 与 DNS/TLS 必须在服务器 staging 先验收，未确认前不得切换 www.deepaha.com。
