# 外部信源资产提交与处理对齐设计

基线：本轮只修改已交付的 DeepAha 3.0.0-rc1 副本。输入端以实际取得的来源资产工作台 v0.3.1 为准，不假定用户本机或远程仓库相同。目标版本 3.0.0-rc2。

## 1. 实际缺口与取舍

rc1 的 `product/sources.py::import_sources` 只接受简化的 sources/source_candidates JSON，且逐项调用正式来源登记；没有 research-handoff.v1 ZIP 接收器、批次预览、研究候选身份/版本、主系统反馈。顶层 agent_acquisition_briefs 没有对齐，不能把旧入口声称为 v0.3.1 对接完成。

v0.3.1 实际导出包含 ResearchHandoff.json、Audit.json、Decisions.json、FeedbackDeclarations.json、Manifest.json 和 originals。它只建议暂存；system_source_id/collection_enabled 为 null。文件里的操作者、评分、官方性、完成状态不是服务器权限或正式来源状态。

选择：在现有 modular monolith 新增小型 `product.scout` 领域模块，复用现有账号/事务/Source/SourceProfile/对象存储/WMA。研究适配器从工具的纯离线模块移植，不复制其 SQLite 数据库、HTTP服务或UI。保留手动上传。资料库与Codex取回仍由原工具负责，本系统不访问ChatGPT私有API、不自动归档或开放探索。

## 2. 输入契约

主路径：v0.3.1导出的研究ZIP。兼容：单个v2.2 Handoff.json、含多个Handoff/State/Review及附件的GPT/WB原研究ZIP。不能以State、Review、ArchiveReceipt或WMA三文件结果代替研究包。普通本地文件经浏览器上传，文件名只是显示/格式信息，不是服务器路径。

外层ZIP上限100MiB、单成员50MiB、总展开500MiB、10000成员、JSON8MiB。成员先验证后读取，拒绝越界、链接、Windows危险路径、加密、重复/大小写碰撞、异常压缩比和重复JSON键。research-handoff外层声明成员逐个验SHA和长度；original_inventory必须完整对应原件。仅明确的originals研究ZIP可再开一层；其中的ZIP附件按不透明原件保存，不递归执行或联网读取。

服务端从originals重新生成投影，不直接信任Audit中的blocking、分数、URL或绑定。Audit和Decisions仅用于展示外部意见与验证交接一致性。原始输入和研究附件保存于现有不可覆盖对象存储，研究材料不自动晋升为官方证据。

## 3. 状态、身份与数据

上传批次：PREPARED → COMMITTED；不可安全读取则 INVALID，保留大小允许的上传原件与错误摘要。预览不会创建正式来源。

候选身份：服务端固定研究台账epoch + 解析出的研究namespace + candidate_key。namespace只是研究族，不证明真实模型。跨族/同URL仅显示已有来源提示，不自动合并。同批所有观察保留；接收只标所选观察。相同原run不同字节记冲突，保留原件但不覆盖首个已接收run，不能批准冲突对象。旧版本晚到不替换已批准来源/Brief。

新增表仅服务接收：scout_batches、scout_runs、scout_candidates、scout_observations、scout_bindings、scout_events、scout_approvals、task_source_contexts。正式Source/SourceProfile继续唯一。新增表通过显式初始化创建，既有数据表不重命名、不改已应用迁移。

## 4. 操作语义

1. 上传并准备：保存原件、重建投影、检查已有run和来源，返回完整批次信息与分页候选。外部“暂缓/不采用”保留，不默认勾选；未完成审核仍允许保存研究资产，但不能冒充已批准来源。
2. 接收所选候选：操作者来自当前登录会话；提交精确preview_hash、选择ID与幂等键。候选、观察、事件、回执在同一短事务提交。重复请求回读同一回执，响应丢失不会要求重新审核。不产生Source/Opportunity/Task。
3. 批准来源：在候选详情一张表单明确名称、原候选入口、来源角色、选用Brief、允许域名及一条原因。正式身份与已有来源重叠时要求显式绑定现有Source；不静默覆盖。变更既有来源要求精确政策版本。默认不启用新任务、不设置自动频率。可在同一批准动作显式允许新任务；无论怎样，本动作不派发WMA。
4. 后续调查沿用现有入口。任务创建时冻结来源政策及选用Brief，Worker使用该快照；政策变化后的未发出任务不会悄悄换Brief继续执行。来源暂停不使旧总览失效。
5. 回执和系统反馈从已提交记录生成。scout-feedback.v1保持工具实际接受的字段、事件与bundle_id。本机环境写STAGING，不能由请求自报PRODUCTION。事件ID稳定，重复下载不制造新事件。工作台离线读取仍显示发行方未认证；文件自报或自带校验值不是签名信任根。

## 5. 前端

电脑管理端增加“来源资产”入口。列表显示批次、候选数、处理结果、接收时间；上传支持拖放及选择文件。详情采用左右区域：候选表（搜索、分页、勾选、外部意见、系统状态）与完整原文/采集建议/问题/历史。只有业务提示，不放原型、开发方案、演练开关或说明性长文。危险问题不遮住其余研究内容。

审核收件箱仅处理WMA结果，不混入来源候选。手机用户端不显示研究批次、操作者、内部记录或后台入口。

## 6. 验收与不做

必须实测：工具实际导出→原件重验→数据库接收→重启回读→批准映射→任务Brief快照→工具读回反馈。覆盖重复提交、同run冲突、未完成包、外部拒绝、伪造审核投影、篡改原件、角色/CSRF、旧版本、来源暂停、研究元数据不泄露。

不扩大至支付、AI匹配、资料库自动连接、自动发现外部来源、旧Provider/逐字段审核、全国扩源或真实WMA付费运行。Windows、PostgreSQL、实际账号资料库、真实WMA仅有实际证据才报通过。

## 7. 实现补充
相同bundle_id且经过字节清单验证的重新压缩包复用原逻辑批次。显式研究分组仅按run_key和原件SHA一致采用，不作为真实作者认证。发送前来源政策变化不会触发远程调用；调查回收/中断反馈始终绑定原任务Brief。rc2增加显式SQLite备份加表命令与反向代理上传边界。
