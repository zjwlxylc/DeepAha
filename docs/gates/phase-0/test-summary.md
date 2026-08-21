# Phase 0 测试摘要

## 新鲜副本环境

- 开始时间：`2026-08-21T16:28:27.5402420+08:00`
- 结束时间：`2026-08-21T16:30:38.4084222+08:00`
- 操作系统：Microsoft Windows 11 家庭版，版本 `10.0.26200`，构建 `26200`
- 提交：`3e55e855879bf65fbf66c2c9bb2127e9f9a73f96`
- uv：`0.12.5`
- Python：`3.14.7`
- Node.js：`24.14.0`
- pnpm：`10.15.0`

## 自动验证结果

| 区域 | 命令 | 实际结果 |
| --- | --- | --- |
| 后端依赖 | `uv sync --locked --group dev` | 退出码 0；从空 `.venv` 安装 33 个包 |
| 后端格式 | `uv run ruff format --check .` | 退出码 0；9 个文件已格式化 |
| 后端 Lint | `uv run ruff check .` | 退出码 0；全部检查通过 |
| 后端类型 | `uv run mypy src tests` | 退出码 0；9 个源文件无问题 |
| 后端测试 | `uv run pytest` | 退出码 0；`6 passed in 1.17s` |
| Web 依赖 | `pnpm install --frozen-lockfile` | 退出码 0；从锁文件安装 445 个包 |
| Web Lint | `pnpm lint` | 退出码 0 |
| Web 类型 | `pnpm typecheck` | 退出码 0 |
| Web 测试 | `pnpm test` | 退出码 0；1 个文件、1 个测试通过 |
| Web 构建 | `pnpm build` | 退出码 0；`/` 静态预渲染成功 |
| 根入口 | `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` | 最终退出码 0 |

## 手动浏览器检查

- 检查时间：`2026-08-21T16:19:49+08:00`
- 桌面和 375×812 窄屏均能看到一级标题、正式标语、中文使命和 Phase 0 状态。
- 窄屏无横向溢出：`scrollWidth=375`，`clientWidth=375`。
- 页面资源请求均指向 `127.0.0.1:3000`；未加载原始 Logo、外部字体或追踪脚本。
- 开发服务器控制台有一条 `/favicon.ico` 404；Phase 0 未制作正式图标，详见 Gate README 的已知风险。

## 远程持续集成

- 运行：[GitHub Actions Run 32467472927](https://github.com/zjwlxylc/DeepAha/actions/runs/32467472927)
- 提交：`4f8e52aaeac5b3dee6e45f34148d74fe50ef3394`
- 触发：`push`
- 开始时间：`2026-08-21T09:21:11Z`
- 完成时间：`2026-08-21T09:21:52Z`
- `backend-quality`：`success`，`2026-08-21T09:21:14Z` 至 `2026-08-21T09:21:33Z`
- `web-quality`：`success`，`2026-08-21T09:21:14Z` 至 `2026-08-21T09:21:52Z`

## Gate 关闭前本地复验

- 开始时间：`2026-08-21T17:22:54.8197903+08:00`
- 结束时间：`2026-08-21T17:23:16.4137248+08:00`
- 命令：`powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`
- 结果：退出码 `0`；后端格式、Lint、类型和 6 个测试通过，Web Lint、类型、1 个组件测试和生产构建通过。

## 安装观察

pnpm 报告默认忽略 3 个依赖构建脚本；没有额外批准脚本，后续测试和生产构建仍成功。该提示不是远程 CI 成功证据。
