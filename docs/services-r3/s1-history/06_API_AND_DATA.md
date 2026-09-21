# 接口与数据契约

所有新增接口位于 `/api/membership`。`GET /plans`、`GET /info`为公开读取；其余需要原登录。写操作需要原 `deepaha_session` Cookie 与 `X-CSRF-Token`。前端不提供username来决定当前用户。POST/PUT数据使用严格模型，多余字段拒绝。

| 接口族 | 作用 | 权限 |
|---|---|---|
| `/me`、`/orders`、`/orders/{id}` | 个人权益、订单、报价确认、取消申请 | 本人；单订单允许维护员查看 |
| `/manage/plans`、`/manage/services` | 创建方案、发布条款新版本、上下架、服务项目 | 维护员 |
| `/manage/orders/{id}/quote`、`confirm` | 定制报价、人工/试用开通 | 维护员 |
| `/manage/grants/{id}/revoke` | 撤销权益，不代表完成退款 | 维护员 |
| `/submissions`、`/{id}/supplement` | 公开网站建议、本人补充 | 登录用户 |
| `/review/leads`、`/{id}/decision` | 整体线索审核 | 审核员或维护员 |
| `/manage/leads/{id}/adopt`、`enable` | 登记/复用来源、明确启用 | 维护员 |
| `/watches/topics`、`/watches/sites`、`/{id}/toggle` | 建立/暂停/恢复本人跟踪 | 有效权益 + 服务端名额检查 |
| `/manage/scan-topics`、`scan-site-publications` | 读取公开投影并产生提醒 | 维护员 |
| `/manage/watches/{id}/prepare`、`/manage/jobs/{id}/dispatch`、`refresh` | 持久授权、原任务交接、回读 | 维护员 |
| `/notices`、`/{id}/read` | 本人会员消息和已读 | 本人 |
| `/manage/audit` | 最近操作记录 | 维护员 |

## 原接口适配
`ProductPort`调用原 `p.add_source`、`p.source_status`、`p.create_task`、`p.task_detail`、`p.catalog`。来源归属的已发布机会查询读取原 Identity→Opportunity→CatalogTarget，并通过原 `_target` 生成公开投影。它不依据域名相似度猜来源，不把未发布候选当机会。

该SQL契约已用SQLite实体夹具执行测试，但原R2模型与迁移结构未运行。`integration.py`是必须逐项对齐的边界文件；不能因接口名字一致就宣称已联调。

## 状态
订单：基础/深度 `PENDING → FULFILLED_TRIAL / FULFILLED_MANUAL`；定制 `REQUESTED → QUOTED → 用户确认PENDING → 开通`。待处理可取消；报价过期必须重报。

线索：`PENDING → APPROVED / NEEDS_INFO / REJECTED`；本人补充将待补充重新转为待审。通过不会创建采集任务、不会发布机会。

任务：`QUEUED → DISPATCHING → CORE_QUEUED / RETRYABLE`，原任务回读可进入运行、失败、需恢复、取消或 `RESULT_PENDING_REVIEW`。未知返回不是成功，不自动无限重试。后续从原已发布投影产生独立机会提醒。

权益不是前端标签：由未撤销的持久grant和[start,end)时间范围动态判定。旧方案快照不被改价覆盖，续购不重置当前期。降档后的超额配置保留，但按稳定顺序只执行新额度内的活动项；用户可暂停旧项调整名额。

## 数据表
`mbr_meta/mutex`负责版本与短事务序列化；`services/plans/plan_revisions`负责服务与条款历史；`orders/grants/idempotency`负责申请与权益；`leads/submissions`负责共享公开线索与私有提交；`watches/jobs/notices/audit`负责跟踪、授权、消息与留痕。共14张新增表。

列表暂为有界读取，不是无限分页后台：用户提交/消息/权益、审核线索/任务通常最多200条，订单管理100条，跟踪管理500条，单次扫描最多1000条跟踪，单主题公开目录最多5000条。超大运营规模前需增加游标分页和分批调度；不能用此首版宣称高规模性能已验收。

## 安全与边界
路径、金额、期限、状态、服务能力、版本及名额服务端校验；幂等键与请求摘要绑定；同订单并发只产生一次权益。用户网站只接受公开域名HTTP/HTTPS标准端口；提交时不抓取，派发时检查DNS全部结果。网络重定向、DNS重绑定、真实浏览器与供应商执行隔离仍需宿主验证。

任意用户备注不直接拼入采集提示词。公开采集说明由审核员撰写。没有收集银行卡、支付密码、第三方登录Cookie等设计需求；不要将这些敏感信息放到自由文本中。

## 已核对的原来源默认值与本地授权门
2026-09-21读取的main快照中，SourceProfile.scheduling_enabled默认为True、interval_hours默认为0。这不构成R2实际运行验收。为避免原默认状态被误当作定制任务授权，本模块另有collection_enabled门，初始为False；只有维护员明确启用本模块来源后才可交接网站任务。不会仅因登记来源或原来源已经启用而跳过此授权。
