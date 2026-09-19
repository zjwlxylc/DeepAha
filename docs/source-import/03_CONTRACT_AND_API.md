# 文件与API对接契约

## 1. 三类输入分别在哪里提交

| 输入 | 页面/接口 | 实际意义 |
|---|---|---|
| `DeepAha_Research_…_r….zip` | 管理 → 来源资产 → 导入研究包 | 首选；承接v0.3.1工具完整导出 |
| v2.2 `Handoff.json` 或含Handoff的GPT/WB ZIP | 同一来源资产入口 | 兼容原研究资料；没有外部决定时只提供候选选择 |
| `opportunities.json / evidence.json / report.md` 及官方原件 | 原审核收件箱的“导入返回” | WMA机会结果，不是来源研究，继续整体审核 |

单独的State、Review、ArchiveReceipt、Feedback不是新来源交接。读取State只作研究上下文，不把累计State中的来源再计一遍。

## 2. v0.3.1研究包

```text
DeepAha_Research_<bundle_id前16位>_r<revision>.zip
├─ ResearchHandoff.json  # deepaha.research-handoff.v1
├─ Audit.json            # 外部研究投影；不是可信事实
├─ Decisions.json        # PROPOSE_STAGING / DEFER / REJECT
├─ FeedbackDeclarations.json
├─ Manifest.json         # 各成员路径、SHA-256、size_bytes
├─ README.md
└─ originals/...         # 原始Handoff/State/Review/研究ZIP和附件
```

服务端检验Manifest对实际成员的完整覆盖；检验original_inventory；重算bundle_id（原件目录、Audit摘要、Decisions、revision和events）。这些检查只证明字节/交接一致性，不证明官方身份、网页当前可用或研究结论正确。

内容始终从originals重新分析。客户端Audit可以作为原件保留，不能注入新的候选、URL、系统ID、分数真值或通过状态。工具的显式研究分组仅在Audit的run_key与原件SHA都匹配时作为分组元数据采用；其余自动分组沿用原工具规则。分组不等于模型或作者身份认证。

## 3. 主系统HTTP接口

前缀 `/api/manage/scout`。全部要求已登录operator；写操作同时要求 `X-CSRF-Token`。操作者只能从服务器会话取得，JSON中的actor/verified/collection_enabled等越权字段不能替代权限。页面与API同源。

| 方法与路径 | 输入 | 输出与效果 |
|---|---|---|
| GET `/capabilities` | 无 | 支持格式、大小、实例、环境及自动批准/派发=false |
| POST `/previews?filename=…` | 原始文件字节，ZIP或JSON；无需Base64 | 保存原件、准备投影；返回batch id、preview_hash、状态、数量、默认建议选择 |
| GET `/batches?offset=0&limit=20` | 每页1–50 | 持久提交记录；内容相同的重新压缩包复用原逻辑批次 |
| GET `/batches/{id}` | id | 当前预览与接收回执；GET不发起调查 |
| GET `/batches/{id}/candidates` | q、offset、limit≤50 | 候选分组、历史数、外部意见、系统状态、已有来源提示 |
| GET `/batches/{id}/candidates/{review_source_id}` | 两个标识 | 完整版本、Brief、研究依据、材料入口和批准版本 |
| POST `/batches/{id}/receive` | preview_hash、selected_ids、request_key | 一个事务接收所选候选；不登记正式Source或创建Task |
| GET `/batches/{id}/receipt` | id | 只读已提交回执；未提交409，不伪造成功 |
| POST `/observations/{observation_id}/approve` | 见下文 | 明确登记或关联正式来源，保存选用Brief；默认不允许新任务 |
| GET `/batches/{id}/feedback` | id | 下载与原工具兼容的系统事件反馈 |
| GET `/batches/{id}/file?name=…` | 返回清单中的材料名 | 授权下载原字节；不解释为服务器路径，不内联执行HTML |

接收请求：
```json
{
  "preview_hash": "从本次GET返回中复制的64位摘要",
  "selected_ids": ["从候选列表取得的review_source_id"],
  "request_key": "调用方为本次意图生成的唯一请求键"
}
```
上面是字段说明，不是可直接使用的样本值。不要编造ID或摘要。审批/接收的身份、候选清单及许可范围由服务端校验。

批准字段：`approval_version`、`binding_version`、`name`、`url`、`tier`、`reason`、`request_key`；可选 `brief_id`、`allowed_hosts`、`enabled=false`、`existing_source_id`、`expected_policy_version`。URL和Brief必须属于当前候选原件。已有来源需明确关联并核对当前政策版本，不能凭同名自动合并。来源角色默认保守，研究者声明不自动提升为官方性。

API的具体参数Schema由当前应用导出至 `openapi.json`。本版没有给原工具旧单批兼容窗口补装 `/api/scout-import/v1`；不要把新的批量研究包发送到旧v1 execute接口。原工具导出 → 主系统网页上传，是已经对齐并验证的正式提交方式。原有单条手工登记及简化JSON CLI仍保留，但研究格式不能借该旧入口自动登记正式来源。

## 4. 幂等、冲突和恢复

相同上传字节重用原记录。工具研究包只是改变压缩方式或统一外层目录，且其已核验bundle_id相同，也复用原逻辑批次；重新上传字节另保留，不重复累计候选事件。

同一研究分组和run_key出现不同原件时，保存冲突，但不覆盖首个已接收run。只影响相关候选；没有冲突的候选仍可接收。晚到旧版本不自动替换已经批准的来源或Brief。

接收提交校验精确preview_hash。在批次/既有来源变化时409，重新GET取得预览，不重新调用WMA。已提交的同一选择意图回读原回执；不得通过更换幂等键覆盖已提交选择。需要改变外部研究选择时在工具中生成新的交接修订，原回执保持历史含义。

批准请求有独立幂等键和内容摘要。冲突键、错候选版本、错绑定版本、错来源政策版本均不覆盖原批准。断网后先查询持久记录，不把HTTP响应丢失当作数据库一定失败。

## 5. 系统反馈

固定格式为原工具已有的 `deepaha.scout-feedback.v1`，包含 `issuer / instance_id / environment / feedback_id / bundle_id / observed_at / events`。字段及事件时间含时区。bundle_id与交接包精确关联。

本版产生：CANDIDATE_RECEIVED、CANDIDATE_REJECTED（run冲突）、SOURCE_APPROVED、SOURCE_SUSPENDED、PRODUCTION_RUN_COMPLETED、PRODUCTION_RUN_FAILED。没有真实合并动作就不编造SOURCE_MERGED。无凭据、闲置和发送前政策变化不冒充一次远程调查失败。

WMA结果回收/整理完成不代表机会审核通过；事件明确 `opportunity_approved=false`。中断后的恢复尝试分别记录，重复下载不增加事件。

离线反馈是服务器导出的记录文件，不是自证签名。原工具仍返回 `authenticity=UNVERIFIED`、`applied_to_official_state=false`；这不是对接失败。应通过原系统授权查询确认，不能把文件自报或本地HMAC当作可信发行方证明。主系统生产环境标记取自部署配置，不能由研究文件指定。

## 6. 限额

上传100MiB、单展开成员50MiB、总展开500MiB、10000成员、JSON8MiB、来源分组2000个、来源观察10000条、candidate_key≤500字符、run_key≤120字符。只打开指定originals研究ZIP一层；里面的压缩附件保留不递归。反馈最多10000事件，超限明确报错而不是截断。

NGINX研究上传专用location允许101MiB，服务器仍执行100MiB；其他路由保留原限额。Node可选同源代理对此上传使用180秒上游等待。实际NGINX/生产代理配置仍须在宿主验证。
