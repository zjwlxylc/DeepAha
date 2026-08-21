# Phase 0 工程基础 Gate

> Gate 状态：`CLOSED`
> 本地验证基线：`3e55e855879bf65fbf66c2c9bb2127e9f9a73f96`
> 远程 CI 验证提交：`4f8e52aaeac5b3dee6e45f34148d74fe50ef3394`
> 证据日期：2026-08-21

## 目标与范围

本 Gate 只验收 Phase 0 工程基础：根工程约束、FastAPI 最小后端、Next.js 最小 Web、统一本地验证入口与 GitHub Actions 工作流。数据库、采集、LLM、规则、用户系统和其他业务能力不在本次范围内。

## 结论

- 本地新鲜副本验收：`PASS`。根验证脚本退出码为 `0`。
- 远程持续集成：`PASS`。[GitHub Actions Run 32467472927](https://github.com/zjwlxylc/DeepAha/actions/runs/32467472927) 在远程提交 `4f8e52aaeac5b3dee6e45f34148d74fe50ef3394` 上完成，`backend-quality` 与 `web-quality` 均为 `success`。
- 最终 Gate：`CLOSED`。本地与远程验证证据均已具备。

Phase 1 的工程进入条件现已满足；本次工作仍严格止于 Phase 0，没有进入 Phase 1。

## 已知风险与观察

1. pnpm 10.15.0 在安装时提示默认忽略 `esbuild`、`sharp`、`unrs-resolver` 的构建脚本；未批准额外脚本的情况下，组件测试、Lint、类型检查和 Next.js 生产构建均已实际通过。
2. Phase 0 按设计不制作正式 favicon。开发服务器浏览器检查中，浏览器对 `/favicon.ico` 的默认请求返回 404；页面没有加载原始 `设计/logo.png`，该观察不改变当前范围。

详细证据见 [验收结果](./acceptance-results.md)、[测试摘要](./test-summary.md) 和 [延期决策](./deferred-decisions.md)。
