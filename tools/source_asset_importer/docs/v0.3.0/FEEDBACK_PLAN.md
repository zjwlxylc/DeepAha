# DeepAha → Scout 真实反馈实施方案
版本：2026-09-13 / v1.0。性质：基于指定代码快照的实施设计，不是生产联调证明。

## 1. 本轮确认的边界

主仓依据为用户的 `DeepAha-main.zip`，SHA-256 `9366410a3aa159fdf615a0e639485411137f2eb2d8b2b14888d207ba3de35d61`，ZIP comment 指向 `d0918ec1245264e271f42a18d54c0fb903000c00`。没有以此冒充实时GitHub HEAD，也没有修改主仓或生产环境。源码规定后端Python `>=3.14,<3.15`；本地导入器Python3.11+与主系统工具链不同。

已核对的现有实现：`backend/src/deepaha/sources/registry.py` 有正式来源契约处理；`api/investigations.py` 处理调查登记；显式运行接口实际位于 `api/investigation_runtime.py`，含 `POST /tasks/{task_id}/dispatch`。新拟议的 `backend/src/deepaha/scout_intake/` 在该快照中不存在。因此不能宣称当前生产服务已能直接接收本次研究交接包。

沿用2026-09-12评估包R0–R7路线：R0核定当前运行基线；R1改善实际审核；R2接入Scout。R2工程可与R1独立推进，但来源启用、联网调查及WMA调用必须另行授权。不新建第二套Source Registry，不回到原生Automation抢任务实验，不等待收费/账户商业化全部完成才收集导入反馈。

## 2. 反馈不是一份“成功”JSON

| 层次 | 真实发生后才能声明什么 | 从哪里产生 | 不能推导什么 |
|---|---|---|---|
| 本地工作台 | 已检查、已写本地意见、已导出 | 当前工具本地记录 | DeepAha收到、来源批准、WMA运行 |
| 候选接收 | 包已持久保存，哪些候选被接收/拒绝 | 主系统R2-C事务提交后的接收记录 | 已启用来源、事实可靠 |
| 来源批准 | 系统Source/Endpoint ID及政策版本 | 主系统R2-D授权决定 | 采集一定成功、公告当前开放 |
| 运行与复核 | 本次用了哪个Brief，回收/核验结果、真实耗时 | 既有Direct WMA运行和人工复核记录 | 对所有未来批次的保证、真人价值 |
| 用户价值 | 实际被展示、用户认为新增、收藏/申请等 | 后续真实用户授权与行为数据 | 由合成用户、文件数量推算的成效 |

“没有回执”记 `NOT_OBSERVED`；未测的耗时、成本、成功率用 `null`。不得用0假装已测为零，更不能把模型自己的confidence当人工确认。

## 3. 与既有R2任务编号衔接（不另造同名路线）

### R2-A / R2-B：接入本轮离线成果
现有本地工具已经产出包安全检查、48批历史规范化、89个候选身份组、原件清单、164条版本引用与辅助意见。主系统仍须自己验包并执行服务端权限/限额；不能相信客户端“通过”即跳过验证。

复用本轮研究适配逻辑，按现有主仓规范移植并重跑单元测试，不复制导入器的SQLite作为新的生产数据库。接收三种输入：原GPT Handoff集合、原WB ZIP、`deepaha.research-handoff.v1`导出包。对后者验证Manifest和原件，再重建服务端候选，而非直接采用Audit.json中的结论。

嵌套规则：研究交接包中 `originals/.../WB-scout.zip` 可在明确研究适配器中再打开一层；WB里面的官方ZIP附件仍作为不透明研究样本，不执行、不递归解析。单包100MiB、单成员50MiB、累计展开500MiB、成员10000作为本轮保护默认值；变化必须写配置和测试。原始GPT State只作引用上下文，不当第二份Handoff再加一次候选。

身份建议：外部研究族 `chatgpt-scout` / `wb-scout` + `candidate_key`；生产另外绑定实际账户/导入主体和台账epoch。两者不同于官方Source UUID。首轮WB必须保留其独立zero_start_bootstrap；不能因同名迁移快照改写GPT历史。

### R2-C：先交付真实候选回执——这是最小有用闭环
拟在 `scout_intake/service.py` / `api/scout_intake.py` 增加接收、预览、显式提交候选和回执查询/下载。接口路径由Codex依据当前仓路由规范定稿，不由外部工具猜测上线端点。

输入：原包SHA、客户端bundle_id、研究命名空间、run_key、所选候选/版本、expected_revision、幂等键。操作者和权限必须由服务端认证上下文取得，不信任文件自填actor。保存原件对象、每次候选观察、完整Brief、证据和原件关系；保留原始字段与规范化提案两层。

事务：原件落地并校验→短事务记录接收→提交成功→从数据库读取已提交记录生成回执。失败不返回“已接收”。幂等重传不新增候选事件；同run不同内容409冲突；客户端bundle_id不相同不能覆盖旧包。

输出回执：instance_id、environment、transaction_id、received_at、package_sha256、bundle_id、run namespace、candidate_key→系统candidate_revision_id映射、接受/拒绝/待补计数与具体原因。此时Source/Endpoint/Opportunity状态不变。管理员点“下载系统反馈”，手工上传给Scout即可；不新增自动回资料库功能。

### R2-D：来源批准后的映射反馈
复用正式registry，由授权来源管理员确认机构身份、来源角色、主入口、其他Endpoint、allowed_hosts、访问规则和频率。客户端“建议暂存”绝不等于授权批准。

每次决定发独立事件：系统Source ID、Endpoint ID与版本、政策版本、操作者/权限审计引用、来源候选revision、状态及事务ID。已有Source只追加有据的Endpoint映射。跨研究族cy.ncss.cn可指向同一个已确认Endpoint，但两套外部候选身份和来源责任仍保留。不同host/www/http/SPA路由未经证据不得静默等同。

撤回候选、暂停Source、合并映射是不同授权行为。退役建议不能直接停生产；历史仍可追溯。没有充分的官方身份、主入口、许可范围就不批准。

### R2-E + 现有调查链：把“建议有用”变成可测事件
优先从本轮6个GPT代表性试点候选中，**人工只选一个获准入口**先跑通：静态研究所、宁波招考、上海SPA、城市申报服务、高职学生机会、全国活动网络各代表一种形态；不是一次启用6个。

一次来源内发现最多两页或20条新链接，仅在批准的host/栏目内。得到具体AnnouncementLead后，人工选定公告/预算，复用现有调查登记与显式dispatch，不把门户首页直接当完整公告调查。保留原有获准样本范围，不借本轮上传自动扩大白名单。

记录实际run_id、task_id、source/endpoint版本、Brief版本、起止时间、停止原因、取回文件/哈希核验、候选事实数、待人工问题、重试和实际token/费用（平台无数据则null）。对Brief效果的评价需要“原建议→现场差异→是否有帮助→谁复核”的记录，不能只写一个成功率。

## 4. 对外反馈交换契约

本包 `schemas/scout_feedback_v1.schema.json` 定义首版 `deepaha.scout-feedback.v1`。它是**拟议交换契约**，不是声称主系统已发布API。事件至少含event_id、type、candidate_ref、occurred_at；Source事件须system_source_id。服务端应同时填交易、版本、证据引用等extensions。

候选引用采用 `producer_epoch::candidate_key`；客户端映射族名与服务端完整epoch时保留明确映射，不能只按裸ID拼接。每条反馈绑定工作台bundle_id；上传原包SHA另外记录。事件以(instance_id,event_id)幂等；相同ID不同内容是冲突。

可信度拆开：字节checksum、格式正确、包绑定正确、发行系统真实性、事件是否已验证。JSON自填issuer=DeepAha或environment=PRODUCTION不证明真实。当前工作台只完成前三项的离线检查，不自动更新Source状态。下一阶段应由受认证的主系统查询对应transaction/event，或验证受信任实例签名；不能把同一文件自带的公钥当信任根。

## 5. 最小验收矩阵

1. 同包提交两次：第二次返回同一已提交接收结果，Source数仍不变。
2. 同run不同内容：拒绝覆盖；两个原件均有审计记录，人工处理冲突。
3. 故意事务回滚：不生成成功回执，Scout保持NOT_OBSERVED。
4. 伪造PRODUCTION JSON：工作台结构可读也只显示未认证，不改映射。
5. 无来源批准：无法创建正式Source、无法越过allowed_hosts发WMA。
6. 使用旧Endpoint政策版本：409或显式要求重审，不能沿用客户端缓存。
7. 有一次真实调查：反馈必须能由系统run_id取回原始执行记录；无记录不记成功。
8. 原始附件哈希/大小不符：保留声明和实测，阻止该材料提升为正式证据。
9. 成本不可得：null且注明缺失来源；不估算成“已发生费用”。
10. 没有真人数据：用户价值指标不出现估算百分比。

## 6. 当前唯一建议交给Codex的任务

先核对用户当前HEAD与上述ZIP commit；不同则只做相关接口差异清单。随后实施R2-A/B离线适配与R2-C候选暂存/真实接收回执这一条最小闭环；不同时启动来源批准、全量扩源和WMA调用。交付数据库反例测试、真实文件离线回放、授权测试、接收回执查询可复验记录，再由用户决定R2-D/E。不自动merge main或部署。

本方案未读取生产DB、未发出真实导入请求、未生成虚假系统反馈。
