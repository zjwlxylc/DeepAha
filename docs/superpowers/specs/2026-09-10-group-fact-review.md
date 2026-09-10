# 单位组字段事实的独立审核链

状态 IMPLEMENTED，本地定向验证通过，候选 CI 待完成。承接组身份与来源管理入口；本批只接组字段候选、独立字段裁决和事实集保存，不接组规则继承、例外放行或个人资格。

GROUP 已有独立 Unit/Version 和完整来源回执。底层 P9B 事实目标 UNIT 表示精确子项身份，不限定 POSITION，可复用 ExtractionRun/Candidate、FactVerificationDecision 和 VersionedVerifiedFactSet；旧 OpportunityUnitSchemaV08 枚举不变。旧调查事实准备与 SQL 只接受公告和已绑定岗位，保持原义。新桥单独保存 GroupFactPreparation 和 Action，锚定 group_binding_id、source_hash、证据 check_id/hash、组 Unit/Version、原始组字段及完整排除分母。不能借用岗位 ID 或向旧 preparation 注入组目标。

准备仅由服务器枚举该 raw group 的全部字段，复用确定性字段规范化、原件检查和持久证据。UNKNOWN/CONFLICT 不升级为已知；UNPROCESSED、不支持字段或未核验原件继续保留，无可机械追溯证据时不产生可批准候选。原字段、quote、locator 和其他层级排除索引保持不变。组字段没有完整性/资格结论。

读、准备、裁决、保存及相同请求重试均先重新校验当前组来源、精确身份/版本、当前证据回执与审核人权限。回执和裁决采用追加历史；字段全部可审核候选终局处理后才能保存事实集，APPROVE 仍须独立 HUMAN、证据支持与优先级通过，未知只能保存 UNKNOWN。组事实集不进入旧规则/岗位快照入口；后续组规则接入需要单独实现与验证。

验收：真实 PostgreSQL 覆盖准确组归属、旧链隔离、无证据/未知/未处理、独立批准、错任务/错组/错候选、来源与身份过期、权限撤销、幂等及数据库绕过写入；旧事实与字段映射回归。API 使用私有严格请求和响应契约。所有工程审核账号为合成场景，不作为真人批准证明；原真实样本继续为 94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED。

实现记录及恢复顺序见 `docs/development/2026-09-10-group-fact-review.md`。实际持久候选、精确证据集合、事实值/状态、依赖指纹与时间在读取、写入及相同请求重试时重新校验。固定交付 Schema 不接受 UNPROCESSED 作为 fact.status；此类未处理状态保留在桥的可处理状态和原因码中，未修改冻结交付枚举。测试通过未知、未支持字段与人工核验引用验证相关边界。
