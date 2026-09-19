# 接口、WMA输入与状态契约

完整路径和参数见本目录 `openapi.json`。这是当前 FastAPI 应用实际导出的描述，不是未来接口草案。主要接口使用 `/api/...`，与原规划的 `/api/v1/review/overview`、`/api/v2/public` 命名不同；旧前端不能仅修改 URL 前缀继续调用，需按当前请求/权限适配。

## 1. 浏览器身份
`POST /api/auth/login` 接收 username/password，返回 username/roles/csrf，并设置 HttpOnly 会话 Cookie。写请求携带 `X-CSRF-Token`。账号开通、停用、重置密码由受控 CLI；是否开放普通注册由环境开关决定，不允许客户端指定管理角色。

读者可以读取允许公开的已收录内容；审核者可以读取待审预览/原件和决定；维护者管理来源、任务和连接。角色可以组合，但没有隐式继承。

## 2. 已有WMA结果导入
`POST /api/intake/{source_id}` 请求体是 ZIP 二进制，非multipart。可选 `notice_url` 指定本份单公告入口。导入者需要 operator；导入不自动通过。压缩包可有一个共同外层目录或唯一嵌套结果目录，核心文件应可唯一定位。
```text
report.md
opportunities.json
evidence.json
artifacts/
  source-page.html
  attachment.xlsx
```
压缩包上限32MiB、单文件20MiB、解压总量100MiB、100个文件；拒绝越界路径、符号链接、重复路径、加密项和过高压缩比。大包应在上游按明确范围拆分，不丢掉后半段来冒充完整。

支持 opportunities 顶层单对象、数组或含 opportunities 数组的对象。根名称采用 opportunity_name/title/name；announcement_level/fields/facts保留条目；units/positions/tracks/children保留各自层级。陌生字段不强制映射为候选规则。示例：
```json
{
  "opportunity_name": "某研究项目招募",
  "opportunity_type": "RESEARCH_PROGRAM",
  "official_url": "https://research.example.org/notices/123",
  "announcement_level": [
    {"field": "最低服务期", "value": "五年", "status": "UNKNOWN", "evidence": []}
  ],
  "units": [{"id": "team-a", "name": "研究组", "positions": [
    {"id": "position-1", "name": "研究助理", "facts": [
      {"field": "学历", "value": "硕士研究生以上", "status": "CONFIRMED", "evidence": []}
    ]}
  ]}]
}
```
这是格式示例，不是待申请的真实机会。推荐原件元数据包含 artifact_id/local_path/url/sha256/status；引用包含artifact_id/quote/locator。未提供或不能读取的原件形成备注，不伪装已定位。

本轮没有取得用户本机实际 WMA 三文件及原数据库，因此只有代表性旧格式适配/模拟传输回归，不能声明全部实际返回格式适配完成。

## 3. 整体审核
`GET /api/review` 返回有界队列；`GET /api/review/{revision_id}?item=0` 返回整包范围和当前一个机会的首段内容。`/content`、`/units`、`/text` 分页继续读取，携带预览哈希 version；每次决定仍覆盖整包，并非逐对象批准。

`POST /api/review/{revision_id}/decision`：
```json
{"decision":"APPROVE","preview_hash":"由预览返回","note":"","request_key":"每次用户决定生成的唯一请求键"}
```
REJECT使用同结构、须有一条原因。请求字段精确以 OpenAPI 为准。响应保存决定及总览链接；相同请求重复回读；旧版本或相反已生效决定返回409，不静默覆盖。

局部字段 PROVEN_WRONG/INVALID/RETRACTED/EXCLUDED 不公开；含明确矛盾则并列原文和来源，关闭相关自动用途。来源全错配、无法辨识对象、关键完整性失败阻断整包。超时和依赖故障不写成人工不通过。

## 4. 总览与个人
| 接口族 | 作用 |
|---|---|
| `/api/catalog` | 关键词、类型、地区、有界分页与读版本 |
| `/api/catalog/{id}`及content/units/text | 公开白名单内容、分段读取 |
| `/api/catalog/{id}/calendar` | 只对当前可确定日期生成全天日历 |
| `/api/me/profile` | 自填偏好，不向外部模型发送 |
| `/api/me/opportunities`、fit | 偏好相关性与不确定资格状态 |
| `/api/me/actions`、feedback | 收藏、准备、申请、等待、完成及结果 |
| `/api/me/reminders`、notifications | 站内日期/变化消息与已读 |
| `/api/me/export`、data | 自己的数据导出/清除 |

列表单页最多50项，详情首段字段50项、子对象20项，单字段文本每段6000字符。服务内部安全上限为一个返回1000个机会/10000个条目；不是无限负载承诺。消息只返回已到时刻的项；未知时间不会生成精确提醒。

## 5. 来源、任务与运维
四个管理接口族为 status/connection、sources、tasks、history；所有需要 operator。连接检查显式触发。GET不派发任务。任务创建 request_key 幂等，预算60–1800秒；未安装SDK/未配置凭据不领取新任务。
恢复只使用已知 runtime/session 或完整已存文件，**不再发送 Prompt**；远端已经发出的任务无法由本地取消保证立刻停止。周期设置为0关闭或6–720小时，执行身份绑定设定它的维护账号，账号撤销后不继续派发。

## 6. Scout资产
`POST /api/manage/source-assets` 或CLI `source-import` 支持顶层 sources/source_candidates 数组。条目接受name/source_name/institution与seed_url/url/canonical_url/recommended_seed、brief/acquisition_brief。完整原资产随导入回执保存；新来源默认暂停，创建任务数为0。不认识的顶层结构明确报错，不能假报导入成功。此版不执行任意Graph Delta/Merge/Retire提案，需先人工整理成已确认来源清单。

## 7. 当前状态边界
整体收录标签独立于 VerifiedFact。当前资格不确定，不复活旧范围审核来生成肯定结果。更新/撤回保留旧版本并失效相关自动用途，但复杂更正作用域/自动官方撤销解释尚未完整接通。原文和操作历史不因来源暂停被销毁。

已有来源再次导入时不会自动覆盖已经采用的Brief/允许域名；原研究资产仍存入导入回执。该版本不提供任意来源配置修订平台。必要调整应在受控迁移中明确完成，不能把保存研究文件冒充已启用新采集策略。
