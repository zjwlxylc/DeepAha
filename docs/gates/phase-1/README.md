# Phase 1 领域契约与原始证据 Gate

> Gate 状态：`OPEN`
>
> 实现状态：`IMPLEMENTED`
>
> 远程 CI：等待当前实现提交的实际运行证据
>
> 本地验证基线：`c05b7d531190eeebffa6ebca4d35278cdc0788fa`
>
> 证据日期：2026-08-21

## 目标与范围

本 Gate 只验收 Phase 1：五个 v0.1 领域契约、PostgreSQL 18 迁移与约束、S3 兼容不可变对象存储、固定官方样本、原始字节幂等导入、证据定位，以及可复现验证入口。

本阶段没有进入 Phase 2：没有实时采集、Source Registry 调度、通用 HTML/PDF/Excel 解析器、LLM、规则或资格引擎、排序、用户系统、业务页面、Redis、向量检索、异步编排或生产云基础设施。

## 当前结论

- 当前工作副本本地验证：`PASS`。根验证脚本退出码为 `0`；后端快速测试 `25 passed, 31 deselected`，Web 为 1 个测试及生产构建通过。
- Phase 1 集成验证：`PASS`。PostgreSQL 18.4 与 Moto 5.2.2 上 `31 passed, 25 deselected`；Alembic 应用 revision `20260821_0001`，`alembic check` 报告无新增迁移操作。
- 故障注入：`PASS`。将固定 SHA 最后一位临时改错后，验证脚本以非零退出，报告 SHA 断言失败，并删除其专属容器与网络；恢复后同一脚本退出码为 `0`。
- 新鲜副本验证：`PASS`。仓库外的新鲜克隆从无 `.venv`、`node_modules`、`.next`、数据库和对象内容的状态运行两条文档化验证命令，均退出 `0`；验证后 Git 状态干净，范围化容器与网络已删除。
- 远程持续集成：等待 `backend-quality`、`web-quality`、`integration` 在当前 Gate 提交上的真实运行结论。

因此实现状态可以标记为 `IMPLEMENTED`，但 Phase 1 Gate 必须保持 `OPEN`。本地证据不能替代尚不存在的远程 CI 证据。

详细证据见[验收结果](./acceptance-results.md)、[测试摘要](./test-summary.md)、[样本来源](./sample-provenance.md)和[延期决策](./deferred-decisions.md)。
