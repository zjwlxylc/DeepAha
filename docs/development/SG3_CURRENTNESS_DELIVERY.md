# SG3 Currentness Delivery

版本：`3.3.0-rc1`  
基线：用户已人工验收通过的 `3.2.0-rc1 / SG2`

## 交付范围

本轮实现：

- Root/Unit lifecycle marker；
- 新旧 Target 精确 diff；
- `UPDATE_PENDING` 与 `MISSING_PENDING`；
- target-scoped deadline/reminder 失效；
- accepted correction materialization；
- explicit child/root withdrawal；
- target history + compare API；
- target-scoped manual withdrawal；
- target-specific Direct WMA RECHECK；
- desktop review change scope；
- mobile currentness + compact version history；
- SG3 虚构复现包。

## 数据库

SG3 **没有新增数据库 Schema 迁移**。复用 SG1 已有 OpportunityUnit / CatalogTarget 版本行。当前性 metadata 保存在 pending revision/current target projection 中；接受更正后以新增 target version 表达，不覆盖历史。

## 真实数据回归

使用用户最初上传的 RC2 WMA 数据副本重新执行 SG1 backup-first projection：

- Root Publication：1；
- Overview Decision：1；
- GROUP：58；
- POSITION：106；
- Catalog Target：106；
- 第二次升级：幂等、无写入；
- 六类 legacy authoritative 表逐行摘要未变化；
- WMA object tree 内容哈希未变化。

详情见 `evidence/sg3/real_sg1_regression.json`。

## SG3 流程验收

虚构 A01/A02 场景已覆盖：

- 只延期 A01；
- A02 不变；
- A01 旧提醒取消，A02 提醒不取消；
- 定向复查只针对 A01；
- 批准延期后新 deadline 生效；
- history/compare 可还原 2026-11-10 → 2026-12-05；
- 手工撤回 A01 只撤 A01。

详情见 `evidence/sg3/api_acceptance.json`。

## 环境边界

当前容器的 Chromium 对 HTTP 导航受 `ERR_BLOCKED_BY_ADMINISTRATOR` 管理策略限制，因此本轮不把原生浏览器截图声明为验收证据。前端由 JS 契约检查 + 真实 FastAPI API 验收覆盖；最终视觉/Windows 行为由用户本地人工验收完成。

历史源码中仍保留部分当前主链不启用的旧模块；SG3 只要求 `deepaha.product` 当前产品模块可编译，不把全历史仓库 compileall 作为本轮 Gate。

## 停止线

本交付停止在 SG3。SG4 Eligibility 必须等待用户人工验收。
