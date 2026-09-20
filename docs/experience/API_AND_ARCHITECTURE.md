# 新增接口与工程边界

产品继续使用同一个 FastAPI/SQLAlchemy 应用、同源 Session/CSRF 和原生前端。旧 GET/PUT 画像、旧 sources/tasks/actions/notifications 数组接口保留响应形态；新 UI 使用独立查询接口。维护员继承审核权限，审核员不能管理来源、连接或账号。

| 方法 / 地址 | 内容 |
|---|---|
| GET `/api/me/profile-state` | `{profile, version}` 一致读取 |
| PATCH `/api/me/profile` | `{expected_version, changes}`；缺席保留，空值按旧白名单校验；版本不符 409 |
| GET `/api/me/action-board` | status/offset/limit；六状态 counts 与当前筛选 total/items |
| GET `/api/me/notification-list` | unread/offset/limit；先筛选后分页，返回总计 |
| POST `/api/me/notifications/read` | `{ids:[...]}`，最多100；全量校验归属后原子标记，可重复；混入他人 ID 整批拒绝 |
| GET `/api/manage/source-search` | q/enabled/health/offset/limit；全量检索，不是当前页过滤 |
| GET `/api/manage/sources/{id}` | 来源详情、真实已存研究建议、检查安排、最近任务 |
| GET `/api/manage/task-search` | q/status/source_id/offset/limit；任务总计、状态计数 |
| GET/POST `/api/me/actions/{target}/items` | 读取或新增个人准备事项 |
| PATCH/DELETE `/api/me/actions/{target}/items/{id}` | expected_version 防覆盖；归属不符不可读写 |
| GET `/api/manage/execution-policies` | 安全绑定摘要、策略、有效并发、在途/状态不明占用、实测全局占用 |
| PUT `/api/manage/execution-policies/{ref}` | expected_version、mode、max_concurrent、queue_limit、task_budget_seconds、new_dispatch_enabled、domain_limit |
| POST `/api/manage/execution-policies/{ref}/inspect` | 服务端读取实际已发布绑定，**不发送调查 prompt** |
| POST `/api/manage/tasks/{id}/remote-ended` | 明确确认+原因，记录人工确认远端结束；不实际调用远端取消 |

所有个人接口都来自当前会话身份，不能传 actor 冒充他人；管理写入保持 operator + CSRF + 同源检查。参数超界、额外字段或伪造 `verified` 被拒绝。

## 五张增量表

`product_profile_revisions` 保存画像修订号，清除个人资料也推进版本，避免旧标签页把已删除数据恢复回来。旧 PUT 仍是整份替换，且同步推进修订号；新 UI 不再发送部分 PUT。

`product_preparation_items` 保存个人清单，绑定账户、具体机会、当时材料版本。默认来源为“用户自写”；只有显式提供且能核对当前原字段的引用才记录官方材料建议。完成事项不会改变资格；材料更新只提示复核，不替用户改文字。导出包含事项，清除个人数据删除事项。

`product_dispatch_policies`、`product_dispatch_validations`、`product_task_dispatches` 分别保存策略、宿主真实验证记录和任务租约/发布绑定快照。只是模型调度控制，不成为公开机会事实。

## 并发与恢复

沿用数据库短事务写锁：SQLite 使用 BEGIN IMMEDIATE，PostgreSQL 使用原产品的事务级 advisory lock。外部网络等待不持数据库锁。领取、限额和租约持久化在同一个写事务完成；长任务独立续约；入库在工作线程处理，避免大文件解析阻塞心跳事件循环。

在发送 prompt 前再检查任务租约、来源最新授权、操作者、总开关。进入 PROMPT_STARTED 先持久化，再调用外部服务。租约过期或请求接收情况不明只进入回收/人工核查，不自动第二次调查；恢复调用只接续会话取文件，不 prompt。迟到的旧 worker 不能越过入库租约边界。

个人清单、调查候选、公开收录仍是不同责任。原整体审核、证据保留、资格判断、推荐排序、日期提取与实验室 Gold 算法未被原型逻辑替代。

## 兼容范围

保留原始账号/邀请/密码恢复、Scout 资产接收/批准/默认暂停/显式启用、用户数据导出清除、机会/公告迁移、周摘要、站内提醒、实验室和部署文件。本轮对部分原测试的静态页面文案断言作等义调整，因为首页中间屏被用户明确删除、行动 UI 被拆入新模块；没有移除业务权限或领域断言。
