# Mobile R3 本次集成发布

用户已人工验收并授权迁移、合并 main、push 和正式部署。先读 `docs/services-r3/INTEGRATION_RELEASE.md`。下方未部署/未验收等描述是原包历史，不能覆盖本次用户授权；实际发布状态以本次回执为准。

# 当前候选：Mobile R3｜订阅、荐源、定制跟踪与网站分享

基于本轮实际上传的R2完整ZIP，SHA256 `929ab1518f53717018864ffc7904600d9d8a4ca3f1bba52a776631e3dbb3f467`。R3是原系统完整整合，不是S1独立演示；未push、未merge、未部署。

先读 `docs/services-r3/RUN_AND_UPGRADE.md`、`DEPLOYMENT.md`、`TEST_REPORT.md`、`CODEX_HANDOFF.md` 和根目录 `CHANGESET_MOBILE_R3.json`。Windows仍用原启动脚本，Python3.13/3.14；数据目录不变。首次 `upgrade-services` 先备份后新增14张表，目录默认为草稿，服务周期运行与外部调查默认关闭。

运行源仅 `backend/src/deepaha`、`backend/src/deepaha_membership`、`web/public/product`。`validation/membership-s1/src` 只是历史测试输入。用 `python scripts/services_r3/verify.py --output evidence/services-r3/local-verify` 验证；源包逐文件核验用 `python scripts/experience/verify_manifest.py`。

R3禁止用SG8-A旧安装脚本直接上线；同名3.8.0-rc1旧发布目录不能覆盖。新代际为 `…-experience1-services1`，不得把R2旧worker直接接R3数据库回退。完整流程见本轮部署文档。

品牌/海报/资格与价值规则/整体审核/Scout边界保留。支付仍为试用或人工核对，不伪装真实支付回调；微信凭据只在宿主环境，真实WMA/PG/微信/实体手机需现场验收。

**以下是原R2及更早版本历史，不代表R3当前状态；旧根目录元数据备份在 `docs/services-r3/r2-metadata`。**

---

# 当前候选：Mobile R2｜手机优先的产品级打磨

基于用户刚验收的 experience-84353c7-20260920 完整包；本轮未推送、未部署。先读 `docs/mobile-r2/RUN_AND_UPGRADE.md`、`CHANGELOG.md`、`TEST_REPORT.md` 和 `CODEX_HANDOFF.md`。启动前核对 `scripts/mobile_r2/build_assets.py --check`。R2 相对父版本新增表为 0，保留累计 experience1 回退安全锁。

Codex 正在发布的父版本不能被本包整目录覆盖；请使用 `CHANGESET_MOBILE_R2.json` 三方核对。以下各版文档作为历史记录保留，不代表 R2 当前发布状态。

---

# 本次候选：experience-84353c7-20260920

基线 `84353c7`。完整体验改善源码交付；**未部署、未推送、未做真实 WMA / PostgreSQL / 真人验收**。
先读 `docs/experience/README.md`、`TEST_REPORT.md`、`RUN_AND_UPGRADE.md`、`RELEASE_AND_ROLLBACK.md`（均在 docs/experience）。
此候选新增五张表，必须先备份后执行 `upgrade-experience`；旧 Worker 不可直接在新任务队列上回退运行。以下保留 SG8-A 历史记录，不代表本候选当前状态。

---

# DeepAha 当前开发入口

## 最新正式站交付（2026-09-20）

继续开发或部署前先读 `docs/beta-access/UI_COPY_CLEANUP.md`（最新正式发布）及 `docs/beta-access/PUBLIC_RELEASE.md`（账号功能首次发布历史）。用户已人工验收，最新正式源码9149e03f，含用户端文案精简、生日输入与本地启动升级修复。正式服务仍命名为staging/8100，指针staging-current。staging域名独立使用staging-isolated/8200，保持d32082ad版本及Basic Auth。发布前仍需实机复核。

当前交付：**3.8.0-rc1 / SG8-A Public Beta 生产化底座**。

基线：**3.7.2-rc1 / SG7.2**。SG8-A 只增加部署、PostgreSQL迁移、备份、staging/production、发布与回退能力；SG1–SG7.2 的正式业务核心继续冻结。

先读：

- `docs/sg8_a/00_START_HERE.md`
- `docs/sg8_a/02_DATA_MIGRATION.md`
- `docs/sg8_a/03_SERVER_DEPLOYMENT.md`
- `docs/sg8_a/04_RELEASE_ROLLBACK.md`
- `docs/sg8_a/05_VALIDATION.md`
- `docs/sg8_a/06_CODEX_DEPLOY_TASK.md`
- `README.md`

产品入口：`deepaha.main:app`；业务模块 `deepaha.product`；前端 `web/public/product`。

## 绝对业务边界

- reviewer 仍只做整体通过/不通过；不恢复逐字段人工审核。
- WMA 只生产 Candidate Facts，不批准 VerifiedFact / Rule / Eligibility。
- SG6.2 `INELIGIBLE` 证据纪律保持不变。
- SG7 Lab 不能回写生产 Opportunity、Eligibility、Ranking、Rule 或审核决定。
- Synthetic Twins 永远不能冒充真实用户证据。
- Eligibility truth 与 Recommendation truth 分开。
- SG8-A 部署工具不能自动批准 Source/Opportunity，也不能通过数据库迁移改变审核含义。
- WMA API Key 只允许通过宿主 `/etc/deepaha/*.env` 注入；源码、迁移包、日志、ZIP禁止包含真实密钥。
- 服务器 production 源码禁止在线编辑；修改必须回到本地代码基线。
- 未经 staging 人工确认，不允许切换 `www.deepaha.com`。

## 必跑验证

- `backend/tests/product` 全业务回归，每个测试文件独立 RC=0；
- `python -m compileall -q backend/src backend/tests/product`；
- product / SG7.2 前端契约；
- SG7.1 两套 independent Gold Oracle；
- SG8-A SQLite backup typed-copy migration harness；
- SG8-A env/systemd/nginx/compose/script 静态契约；
- 本地真实 HTTP `/health/live /ready /` Smoke；
- 最终包真实 WMA Key/Agent ID 精确 0 命中。

## 宿主实机 Gate

当前容器没有 PostgreSQL server、Nginx 或 systemd 可用实例，因此真实宿主 Gate 只能由 Codex 在服务器 staging 执行：PostgreSQL 迁移、systemd、Nginx/TLS、backup/restore drill、WMA server binding。任何一项未通过都不得切 production。
