# SG7 自测与验收记录

## 1. 后端全产品回归

最终代码对 `backend/tests/product/test_*.py` **逐文件独立启动 pytest**。

原因：本项目既有环境中存在 pytest 长进程跨文件结束阶段偶发不退出的问题。为避免把“断言显示通过”误当成 RC=0，本轮以每个测试文件独立进程的真实退出码为准。

结果：

- 测试文件：26；
- tests：216；
- failed files：0；
- 每个文件：`RC=0`。

机器证据：

- `evidence/sg7/product_regression_final.json`
- `evidence/sg7/product_files_final.tsv`

## 2. 静态与前端契约

PASS：

- Python compileall：product 模块与 product tests；
- `node --check`：SG7 UI / workbench / user；
- `check-product.mjs`；
- `check-sg5.mjs`；
- `check-sg5-1.mjs`；
- `check-sg6.mjs`；
- `check-sg6-1.mjs`；
- `check-sg7.mjs`。

证据：`evidence/sg7/static_and_frontend_checks.txt`。

## 3. 真实 HTTP Smoke

使用隔离 SQLite 数据目录启动真实 `uvicorn` 服务，不触碰用户数据。

验证：

- `/health/live` → `3.7.0-rc1`；
- 实际 Cookie + CSRF 登录成功；
- operator Lab API 可访问；
- 100 Synthetic Twins 存在；
- Gold Benchmark：1 个锁定 Case × 100 Twins = 100 pairs；
- `unsafe_recommendations=0`；
- 资格 Pair Truth accuracy = 1.0（仅 1 条 operator smoke truth）；
- 推荐 Pair Truth accuracy = 1.0（仅 1 条 operator smoke truth）；
- `real_gold_pairs=0`，因此**没有把工程标注冒充独立人工 Gold**；
- `llm_used=false`；
- `production_mutated=false`；
- Founding User：NOT_JOINED → ACTIVE → WITHDRAWN 正常。

证据：`evidence/sg7/http_smoke_final.json`。

## 4. WMA

SG7 Benchmark 本身不调用 WMA，也没有修改现有 Direct WMA 调用协议。

本容器缺少锁定的 `codebuddy-cloud-agent-sdk==0.3.4`；尝试从包源安装时因当前运行环境 DNS/外网不可达而失败。因此本轮没有做新的 live WMA binding probe，也没有发送调查 Prompt、没有产生新的 WMA 调查成本。

这不是 SG7 功能失败，但**不能写成“WMA live test PASS”**。Windows 本地继续沿用用户已有的加密 WMA 配置即可。

## 5. 浏览器视觉自动化

当前容器中的 Chrome 对 localhost/映射 hostname 返回管理策略阻止，无法完成真实 Playwright 截图验收。因此：

- 前端代码、路由、DOM 契约和响应式规则已自动验证；
- 不冒充浏览器视觉验收通过；
- 最终视觉与操作感受由用户在 Windows 本地实际查看。

## 6. 安全与凭据

SG6.2 原始源码包中发现一份历史 WMA 凭据文本。SG7 交付前已删除，并对最终工作树做精确密钥扫描。

交付原则：

- API Key 不进入代码；
- 不进入文档；
- 不进入测试 evidence；
- 不进入 ZIP；
- WMA Agent/API Key 继续使用用户本机数据目录中的安全配置或宿主环境变量。

## 7. 当前 Verdict

**SG7_ENGINEERING_SELF_TEST=PASS**

但发布状态仍是：

**SG7_LOCAL_USER_ACCEPTANCE_CANDIDATE**

原因：真人价值验证和用户 Windows 视觉/操作验收还没有发生。
