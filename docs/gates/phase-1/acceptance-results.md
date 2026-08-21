# Phase 1 验收结果

> 实现提交：`c05b7d531190eeebffa6ebca4d35278cdc0788fa`
>
> Gate 状态：`OPEN`
>
> 远程 CI：等待实际运行证据

## 退出条件逐项结果

| # | 退出条件 | 状态 | 实际证据 |
| --- | --- | --- | --- |
| 1 | 同一捕获内容重复导入只保留一个 `RawArtifact` | `PASS` | `test_replaying_same_capture_returns_same_raw_artifact` 两次调用返回同一 ID，第二次 `created=False`，数据库计数为 1；`test_official_sample_round_trips_raw_bytes_and_separates_domain_entities` 对固定官方样本重复证明。工作副本运行 `scripts/verify-phase1.ps1` 时集成测试为 `31 passed`。 |
| 2 | 原始字节、URL、抓取时间、哈希、bucket 与对象键共同复现输入 | `PASS` | 官方样本纵向测试从 S3 回读并逐字节比较 11,662 字节 fixture，复算 SHA-256；manifest 固定请求/解析 URL 与 `2026-08-21T09:59:08.005Z`；对象键为 `raw/sha256/15/1589…9d2b`。 |
| 3 | `Document` 与 `Opportunity` 是不同实体 | `PASS` | `test_document_and_opportunity_have_distinct_contract_fields`、`test_document_and_opportunity_are_distinct_tables` 及官方样本纵向测试分别证明契约字段、数据库表/列、ID 和标题均分离，`Opportunity` 无 `document_id`/`artifact_id`。 |
| 4 | Schema、迁移、ORM 与契约测试一致 | `PASS` | `test_checked_in_schemas_match_deterministic_renderer` 校验确定性 Schema 导出；`test_schema_fields_map_explicitly_to_persistence_columns` 校验字段映射；`test_migration_matches_orm_metadata` 与 `uv run alembic check` 均报告无差异。 |
| 5 | 新鲜环境可复现全部结果 | `PASS` | 在仓库外新鲜克隆 `C:\Users\LENOVO\AppData\Local\Temp\DeepAha-Phase1-Gate-c05b7d5`（源提交 `c05b7d5…`）从无项目虚拟环境/依赖/构建/存储内容开始运行 `scripts/verify.ps1` 与 `scripts/verify-phase1.ps1`，两者退出码均为 0；结果为快速测试 `25 passed`、集成 `31 passed`、Web `1 passed`、迁移 `20260821_0001` 且无漂移。 |
| 6 | 未加入 Phase 2 能力或禁止产物 | `PASS` | `git diff --stat 22f11b8…HEAD` 显示 52 个文件均属于契约、数据库、对象存储、样本、测试、验证或文档；跟踪产物扫描为 0。私钥/AWS key 扫描为 0；DSN 的 9 个匹配全部是指向 `127.0.0.1` 的已标注测试常量、测试断言或计划文本。运行时代码没有 Phase 2 采集/解析/LLM/规则/用户能力。 |

## Gate 判定

六项退出条件都具有本地与新鲜副本实际证据，但远程 CI 尚无当前 Gate 提交的运行证据。总结论仍为 `OPEN`；不能用本地 PASS 替代远程 job conclusions。
