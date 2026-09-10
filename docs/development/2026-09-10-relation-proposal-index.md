# 桌面审核的持久化导航入口

新增私有 `GET /api/v1/local-human-test/investigations/{task_id}/unit-plans/{plan_id}/relation-proposals`，从数据库按岗位列出提案 ID、生产者 ID、创建时间；按创建时间和 UUID 稳定排序。只返回导航身份，不复制摘要、关系结论或审核状态。进入已有详情接口时再读取当前完整历史和 STALE 状态，防止列表上的旧批准被当作当前结论。

服务复用真人权限、任务/岗位归属与当前来源检查，读取结束再次检查；依赖现有私有访问门和 no-store。未增加迁移，没有修改冻结提案、审核记录或资格规则。

验证：数据库/API 测试从空列表开始，创建两个提案、列出并逐个重新打开，错误任务/岗位返回 404（22.42 秒）；证据 `evidence/2026-09-10-relation-proposal-index.xml`。新增路由的关闭入口、无关角色、未登录三项定向测试通过（2.48 秒）；证据 `evidence/2026-09-10-relation-index-gates.xml`。定向 Ruff 和 mypy 通过。未重跑无关测试或构建。

此入口是桌面页面的依赖，尚不等于页面已完成。下一步接列表导航与详情审核表单，需覆盖刷新后的稳定地址、失败隐藏旧内容、原 nonce 重试、历史与当前状态分离，以及原文证据入口。工作分支 `codex/relation-proposal-index` 基于 PR #44；父批 CI 全部通过前不合并。
