# 私有关系审核 API

为已实现的冻结提案与独立审核历史提供三个接口，均位于 `/api/v1/local-human-test/investigations/{task_id}`：

- `POST /relation-proposals`：接受 ProposeRelation，必须提供 Idempotency-Key。
- `GET /relation-proposals/{proposal_id}`：返回完整历史和当前回放。
- `POST /relation-decisions`：接受 DecideRelation，必须提供 Idempotency-Key。

三个接口复用现有私有开关、认证与人工审核权限。服务端仍负责证据、任务归属和历史完整性，不信任客户端提供生产者或审核者。自审返回 403，缺失任务/提案返回 404，状态或前驱冲突返回 409。请求结构错误沿用本项目私有接口的 400，不采用 FastAPI 默认 422。

响应直接转发服务验证过的 JSON 字典，不用类型模型重新序列化冻结包；`proposal_payload_sha256` 是后续请求使用的稳定提案摘要，`payload_sha256` 是当前完整包摘要。旧审核请求重试保留原收据，但返回最新回放。审核后仍 `executable=false / UNCERTAIN`。

在现有 HTTP middleware 中为 `/api/v1/local-human-test/` 统一设置 `Cache-Control: private, no-store`，包含路由执行前的鉴权、请求格式错误及数据库异常。新增未登录测试先发现旧异常路径缺此标记，然后修复；不修改公开接口缓存策略。

## 实际验证

- `evidence/2026-09-10-relation-api-gates.xml`：42 项通过，含新增 9 项开关/角色/未登录测试和既有 investigations API 回归。
- `evidence/2026-09-10-relation-api-roundtrip.xml`：真实服务/PostgreSQL 的创建、读取、自审拒绝、身份注入拒绝、独立批准、刷新修订、旧请求重试、错误任务/提案与摘要回放通过（25.42 秒）。这是增加参数化前的常规样本，相关行为未改变，复用其证据。
- `evidence/2026-09-10-relation-api-float.xml`：仅新增 `with_float=True` 样本定向通过（23.99 秒）；验证来源包含 `1.0` 时完整包转发仍与摘要一致。未重复执行常规样本。
- Ruff 格式/检查、定向 mypy 通过。独立只读代码评审未发现 P1/P2，评审者未运行数据库测试。未重跑整站测试、构建或 WMA。

## 独立记录的旧限制

额外把浮点夹具设为 `1e-7` 时，在 setup 的 `investigation_evidence_checks` INSERT 即触发 `Invalid investigation evidence check`（函数 `investigation_evidence_check_guard`），尚未进入上述三个新 API。该旧 JSONB 摘要路径不能据此宣称支持指数表示；本批仅验证当前支持的 `1.0`。复现方式：将本测试 float_files 中两个 weight 值同时由 1.0 改为 1e-7 后单跑 `-k True`。未修改旧 guard 或降级校验，后续单独处理其冻结表示迁移边界。

## 集成顺序

本批基于 `4ffcf85e7b2527d13fb2c6bf110db8e8461dc26c`（PR #43）。先等其精确候选 CI 全部通过并合并，再将本批作为独立 API 变更集成。随后接桌面审核页面；旧指数格式限制须作为独立数据持久化问题处理，不混入 UI 工作。
