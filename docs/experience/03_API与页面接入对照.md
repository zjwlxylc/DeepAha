# 页面、交互与真实 API 对照

基线：`84353c7e5286e276d24af8e0342d4d3441c30ec5`。本文中“现有”表示已读到定义；“拟新增”不是已经存在的接口。原型的 `P.state`、`Domain`、数字 `version`、`remotePrompts`、`prototype` 标记均为演示模型，不能直接作为生产数据库或安全契约。

## 一、前端入口与文件复用

当前入口是 `web/public/product/index.html`，加载 `brand-v2.css`、`product.css`、`access.css`、`icons.js` 和模块脚本 `app.js`。业务页面分布于 `user.js`、`workbench.js`、`access-ui.js`、`scout.js`、`lab-ui.js`；共同能力在 `core.js`。

本交付中的 `prototype/pages-user.js` 和 `pages-ops.js` 是布局和行为参考，不建议原样整体覆盖现有文件。按工作流逐步替换模板，复用现有请求、转义、角色判断、日期、分页和证据渲染。`domain.js` 仅为原型防误演示，不可取代生产 Eligibility、Ranking、来源授权和审核逻辑。

生产 CSP 的 `script-src 'self'` 不允许此单文件 HTML 的内联脚本。生产时拆成同源静态文件，不为上线原型而允许任意内联 JS。保留现有 `/product/brand-logo.png` 图形标志和 favicon；本稿只使用离线字标，不是批准换标。

## 二、已存在的主要读写接口

| 页面／动作 | 当前接口 | 关键对接要求 |
|---|---|---|
| 站点功能开关 | GET `/api/site` | `public_catalog` 与注册模式决定实际入口，不能从演示角色推断 |
| 机会总览 | GET `/api/catalog` | 现有 q、kind、region、offset、limit、read_version；limit 最大 50 |
| 具体机会详情 | GET `/api/catalog/{id}` | 读取具体 target，而非把父公告作为任意岗位 |
| 父公告 | GET `/api/announcements/{id}` | 展示共同内容及可访问的分项 |
| 长内容、分项 | GET `/api/catalog/{id}/content`、`/units`、`/text` | 保留版本参数；409 时不能拼接不同版本的内容 |
| 更新记录 | GET `/api/catalog/{id}/history`、`/compare` | compare 使用 from_id、to_id；新版未收录不覆盖旧值冒充已确认 |
| 日历导出 | GET `/api/catalog/{id}/calendar` | 仅在后端确认时间可用时开放；冲突、待更新、未知不捏造日期 |
| 个人推荐 | GET `/api/me/opportunities` | 读取服务端资格与优先级，不从卡片配色反推资格 |
| 资格与价值 | GET `/api/me/fit/{id}`、`/value/{id}` | 两个不同结论；证据定位与风险原样保留 |
| 画像 | GET / PUT `/api/me/profile` | 当前 PUT 整份替换；局部表单不能只提交可见字段 |
| 行动记录 | GET `/api/me/actions`；PUT / DELETE `/api/me/actions/{id}` | PUT 为 status、note；六状态枚举沿用现有值 |
| 行动历史、周摘要 | GET `/api/me/actions/{id}/history`、`/api/me/weekly-digest` | 当前页计数不是总计；存量公告级行动不得猜测迁成任意具体分项 |
| 结果与有用性反馈 | POST `/api/me/feedback/{id}` | 使用现有 outcome 与 useful 等字段，个人自由文本不进入公开事实 |
| 提醒 | POST `/api/me/reminders/{id}` | days_before 1–30；整体偏好在 profile 中 |
| 消息 | GET `/api/me/notifications`；POST `/api/me/notifications/{id}/read` | “全部已读”并无已核实批量接口；逐条提交须有部分失败处理，或另加批量契约 |
| 个人导出／清除 | GET `/api/me/export`；DELETE `/api/me/data` | 成功后清理前端相关缓存；不能删除公开收录与他人资料 |
| 审核收件箱 | GET `/api/review` | status、q、offset、limit 与 total 已有，继续使用 |
| 审核预览与长材料 | GET `/api/review/{id}` 及 `/content`、`/units`、`/text` | item、version、offset；整份返回的范围不能因分页被误缩小 |
| 原始附件 | GET `/api/review/{id}/file` | name 由服务端已保存列表提供，不能让 URL 参数直接读任意文件 |
| 整体决定 | POST `/api/review/{id}/decision` | decision、preview_hash、note、request_key；preview_hash 是 64 位十六进制，不是原型的 v1 |
| 具体机会撤回 | POST `/api/catalog/{id}/withdraw` | reason 与 expected_publication；不能误撤同一父公告的其他分项 |
| 收录管理 | GET `/api/review/catalog/summary`、`/groups`、`/groups/{root_id}/targets`、`/targets` | 复用已有聚合与筛选；父公告和具体目标有不同计数 |
| WMA 返回包接收 | POST `/api/intake/{source_id}` | 原始 ZIP；接收后产生待审核预览，绝非自动公开 |
| 来源列表／登记 | GET / POST `/api/manage/sources` | GET 默认 50 条；POST name、url、brief、allowed_hosts |
| 来源授权启停 | PUT `/api/manage/sources/{id}/status` | enabled、reason、expected_version；暂停不撤回已有公开内容 |
| 来源周期 | PUT `/api/manage/sources/{id}/schedule` | hours 0–720；0 为手动；非零会创建真实调查，须明确确认 |
| 调查列表／新建 | GET / POST `/api/manage/tasks` | POST source_id、url、instruction、kind、request_key、budget_seconds；预算 60–1800 秒 |
| 调查详情 | GET `/api/manage/tasks/{id}` | source_context 已可返回；适合展示“本次调查采用的来源快照” |
| 恢复／停止 | POST `/api/manage/tasks/{id}/recover`、`/cancel` | 恢复不再次 prompt；本地停止不保证远端停止 |
| 系统状态 | GET `/api/manage/status` | 数据库读取、对象目录可读、worker 心跳、连接配置不混为一种健康 |
| 连接与探测 | PUT `/api/manage/connection`；POST `/api/manage/check-connection`、`/check-storage` | 正式环境连接秘密由宿主管理；检查连接只读取发布绑定，不是完整调查验收 |
| 审计与反馈样本 | GET `/api/manage/history`、`/feedback-candidates` | 只显示必要内容；不要把内部 ID 当用户可理解的标题 |

来源周期及任务创建的准确路由以基线 `api.py` 和 `workbench.js` 为准，计划新增的搜索参数不可静默发送给旧接口并误以为已过滤。

## 三、来源资产：三次不同性质的动作

现有 `scout_api.py` 路由：

```
GET  /api/manage/scout/capabilities
POST /api/manage/scout/previews?filename=...
GET  /api/manage/scout/batches
GET  /api/manage/scout/batches/{id}
GET  /api/manage/scout/batches/{id}/candidates
GET  /api/manage/scout/batches/{id}/candidates/{candidate}
POST /api/manage/scout/batches/{id}/receive
GET  /api/manage/scout/batches/{id}/receipt
GET  /api/manage/scout/batches/{id}/feedback
GET  /api/manage/scout/batches/{id}/file
POST /api/manage/scout/observations/{id}/approve
```

接收请求包含 `preview_hash`、`selected_ids`、`request_key`；批准请求另需 `approval_version`、`binding_version`、机构与入口、tier、reason、request_key、允许域名及可选的既有来源绑定。`enabled` 默认 false。接收只保存候选，不应自动批准；批准来源也不应隐式立即调用 WMA。

原型可读取 `prototype/sample-scout.json`，其 schema 为 **DeepAhaPrototypeScout/v1**，仅验证本地预览→接收→批准的交互。它不是正式 Scout/Handoff 格式，不是外部导入工具的新协议。正式接入必须根据 capabilities 使用现有原始包处理器，保留真实回执与反馈文件。归档到 ChatGPT 资料库不等于导入本系统数据库。

## 四、账号与实验室

现有账号管理入口由维护员授权：`/api/admin/invitations` 创建／读取，`/{id}/revoke` 撤销；`/api/admin/users` 读取，`/{id}` PATCH 修改 active/roles/reason；`/{id}/revoke-sessions` 与 `/{id}/password-reset` 为显式 POST；账号审计 `/api/admin/audit`。登录、邀请注册、修改密码、重置密码继续走 `/api/auth/*`。

角色值仍为 `user`、`reviewer`、`operator`；维护员继承审核能力，普通审核员没有来源、任务与账号权限。前端隐藏不是鉴权；后端必须验证请求。原型切换身份只是预览工具，正式版删除整个工具条，不提供角色切换器。

实验室现有 `/api/manage/lab/summary`、`/twins`、`/gold`、`/runs`、`/founding-metrics` 及样本配对真值、锁定等接口；用户参与使用 `/api/me/lab`、`/join`、`/leave`。原型实验结果只测演示约束，不替换真实 Gold Oracle，不执行 SG7 数据写回生产。

## 五、拟新增契约：先测试，再接界面

### N01｜带版本的画像局部更新（建议新增）

不改变旧 PUT 的既有语义。新增端点拟为 PATCH `/api/me/profile`，请求 `{expected_version, changes}`；GET 通过 ETag 或显式版本元数据给出版本，但必须设计向后兼容，不能把原本直接返回画像的接口突然换成 envelope 破坏旧页。

- changes 只允许现有 PROFILE_KEYS；缺席字段保留，空字符串／空数组表示按对应字段规则显式清空。
- 权限和字段验证复用 PersonalMixin；通知同步、审计只在成功提交后运行。
- 同一事务比较 expected_version，不一致返回 409 PROFILE_CHANGED，返回可安全展示的冲突提示。
- 生日继续 YYYY-MM-DD；日期合法性与未来日期检查仍由后端负责。
- 新增版本存储必须有备份、迁移及兼容回退；上线前未实现时只使用完整对象 PUT，且明确暂不具备跨标签页冲突保护。

### N02｜来源与任务列表的服务端查询（建议新增独立查询入口）

为避免旧调用方期望数组而被破坏，拟新增只读查询入口，如 GET `/api/manage/source-search` 与 GET `/api/manage/task-search`；名称可在正式设计时统一，但不得同时维护不同语义的重复真源。

请求限定 q、status/enabled、source_id、offset、limit；返回 `{items,total,offset,limit,has_more}`，有稳定次序和明确上限。q 用参数化安全查询，计数和筛选基于同一条件。来源“健康”不能只用一个布尔值，应分别表示授权开关、最近回收结果和待处理异常；最后成功回收不等于最后成功公开，也不等于公告已最新。

列表页保留 URL 查询参数。新增任务选择器支持远程搜索并按 ID 读取选中项，不能局部页面过滤后声称搜索了全部来源。

### N03｜执行策略及能力验证（新增后端，不是现有 WMA API）

建议服务端记录以下逻辑字段；这是内部控制数据，不是发给供应商的请求字段：

```json
{
  "policy_id": "internal-policy-id",
  "policy_version": 1,
  "connection_ref": "host-managed-binding-reference",
  "binding_fingerprint": "server-computed-nonsecret-fingerprint",
  "mode": "SERIAL",
  "max_concurrent": 1,
  "task_budget_seconds": 1200,
  "queue_limit": 20,
  "new_dispatch_enabled": false,
  "validation_run_id": null
}
```

校验状态、供应商分类和 binding_fingerprint 只能由可信服务端检查得到。**生产请求不接受浏览器提交 `verified:true` 作为凭证。** 原型的“并发已验证场景”只是展示通过后的控件状态。AGENS 按项目策略始终 1；其他未核验连接也为 1。验证绑定变化使原校验失效。并发初期建议逐级从 2 验到 4；4 是本次保守试验上限建议，不是供应商事实。

调度侧至少需要原子领取、lease_owner、lease_expires_at、task 状态比较更新、连接级配额、来源域限与 frozen policy version、prompt 已发送检查、回收专用路径。远端是否已接收不确定时进入人工核查／文件回收，不自动发第二次 prompt 来“求稳”。修改策略只影响明确范围的新任务，不能改写在途任务的冻结上下文。

真实验证分两步：无调查的 inspect_release；获得用户授权后，再对有限官方来源执行带预算的隔离端到端调查。记录完整结果回收、延迟、资源上限、取消含义和错误恢复，不只是 HTTP 200。任何失败可退回串行；不能借降低 gate 放行。

### N04｜用户个人准备事项（原型已展示，正式需新增）

现有 ActionInput 只有 status/note；本稿复选清单不能假装已被当前后端保存。建议每条个人事项关联 account_id＋target_public_id，保存 id、text、done、origin、version，origin 区分用户自写与从官方材料形成的建议，并保留对应材料版本。个人增删不能改写公告事实。更新用版本校验；用户数据导出／清除包含这些事项。

第一批不增加该接口时，正式界面可以先保留“备注与行动状态”，不要上线点击后刷新即丢的伪清单。

## 六、必须从服务端获得而不是由前端猜测的值

资格与不符合依据；当前时间可用性；具体目标身份与发布版本；审核是否允许整体通过；来源授权和域名范围；内容变更是否影响旧事实；连接能力与预算；账号权限；全量计数；实验样本真值来源。原型为排版演示这些值，不构成计算规则规范。

## 七、错误与加载契约

401 清除失效会话并带回原路由；403 保留清楚的权限说明；409 按 preview/source/profile/publication 冲突分别解释并要求读取当前版本；410 表示已退役或撤回，不渲染成空白；429 说明何时可重试，不在后台密集循环；网络中断保留用户已输入内容并禁止不确定提交状态下重复发起付费动作。空列表、加载失败与没有权限是三种不同页面状态。

敏感写操作以 request_key 和预览版本组合支持安全重试；后退、刷新、重复点击不能创建额外决定、来源或远端调查。不能把重新渲染整个表单作为通用错误恢复，避免丢失未保存输入。
