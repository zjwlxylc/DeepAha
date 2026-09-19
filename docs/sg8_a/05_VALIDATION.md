# SG8-A 验证记录

版本：**3.8.0-rc1**。

## 1. 完整产品回归

`backend/tests/product` 当前共：

- **30 个测试文件**；
- **227 tests**；
- 每个测试文件独立 pytest 子进程执行；
- **30/30 文件 RC=0**；
- failed files = 0。

证据：`evidence/sg8_a/product_regression.json`。

## 2. SG7.1 Gold Oracle 回归

资格独立 Gold：

- 6 个确定性题 × 100 V2 twins = **600 pairs**；
- `truth_accuracy = 1.0`；
- `unsafe_recommendations = 0`；
- `llm_used = false`；
- `production_mutated = false`。

推荐独立 Gold：

- 20 个题 × 100 V2 twins = **2000 pairs**；
- `FEATURE → FEATURE = 371`；
- `HOLD → HOLD = 1629`；
- mismatch = 0；
- `recommendation_accuracy = 1.0`；
- `unsafe_recommendations = 0`。

证据：`evidence/sg8_a/oracle_eligibility.txt`、`oracle_recommendation.txt`。

## 3. SG8-A portable migration harness

当前执行环境没有 PostgreSQL server，因此不能把“真实 PostgreSQL 迁移”写成已通过。

已经实际执行同一套 SQLAlchemy typed-copy 算法的 SQLite→SQLite harness：

- **41 张当前 DeepAha 表**；
- account/password hash 保留；
- browser session 在 backup restore 阶段撤销；
- object bytes + metadata 被复制并 SHA256 复核；
- 目标 DB / object store 非空时拒绝覆盖；
- credentials_migrated = false。

证据：`evidence/sg8_a/migration_harness.json`。

真实 PostgreSQL Gate 必须在 `staging.deepaha.com` 所在宿主完成。

## 4. 静态与运行检查

已通过：

- `python -m compileall -q backend/src backend/tests/product`；
- `web/scripts/check-product.mjs`；
- `web/scripts/check-sg7-2.mjs`；
- `bash -n ops/sg8a/*.sh`；
- `infra/sg8a/compose.dev.yaml` YAML 解析；
- 真实本地 HTTP API 启动；
- `/health/live = 3.8.0-rc1`；
- `/health/ready = database_read: ok`；
- `/` 可访问。

## 5. 安全扫描

使用用户单独提供的真实 WMA API Key / Agent ID 作为只读比对值：

- 源码树 API Key 精确命中：0；
- 源码树 Agent ID 精确命中：0；
- `.env / deepaha.db / wma-connection.enc / .credential-key` 运行时敏感文件：0；
- 已有嵌套 ZIP 共扫描 21 个 archive，真实凭据命中：0。

证据：`evidence/sg8_a/security_scan.json`、`nested_archive_security_scan.json`。

## 6. 当前环境不能声称 PASS 的项目

以下必须由实际服务器 Codex 执行：

- PostgreSQL 真实空库迁移；
- `pg_dump / pg_restore` 宿主命令；
- systemd 模板实际启动、自启、重启；
- Nginx TLS / rate limit / staging Basic Auth；
- staging DNS；
- staging → production Nginx 切换；
- 服务器 WMA SDK + Agent binding（如本轮决定启用）；
- 真实 backup → empty-target restore drill。

因此 SG8-A 当前状态是：

> **工程自测 PASS / staging 宿主实机验收候选**，不是“已经部署上线”。
