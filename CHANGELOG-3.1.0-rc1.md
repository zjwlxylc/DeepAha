# 3.1.0-rc1 · SG1 可行动机会粒度

本版在 3.0.0-rc2 + Direct WMA 联通基础上完成 SG1，不进入 SG2。

## 主要变化

- 一份父公告可物化多个用户可行动 Catalog Target；POSITION / TRACK / PROGRAM_TIER / REGION_VARIANT 成为总览卡基本单位。
- GROUP 只作为单位/范围上下文，不出总览卡。
- 父公告继续承担整体审核、版本、证据与历史上下文；人工仍只做一次整体 APPROVE / REJECT。
- 用户收藏、反馈、截止提醒迁到 target 粒度；不同岗位互不污染。
- 目标详情区分岗位自身内容、单位/分组共同内容、公告共同条件，并保留父公告入口与同公告其他机会。
- 新增 backup-first `upgrade-sg1`，对 rc2 SQLite additive 建表和回填，不改写原 Root Opportunity / Publication / Decision / WMA 原件。
- 启动器检测 rc2 数据目录后自动执行幂等 SG1 升级检查。
- 修复 root-only singleton 日历导出的 target identity。

## 用户上传真实数据复现

1 个根公告 + 58 个 GROUP + 106 个 POSITION：升级后仍为 1 个 Publication / 1 个 Decision，同时生成 164 个 Unit identity 与 106 个 POSITION Catalog Target。机会总览实际回读 `total=106`。

完整证据见 `docs/sg1/05_REAL_WMA_VALIDATION.md` 与 `evidence/sg1/`。
