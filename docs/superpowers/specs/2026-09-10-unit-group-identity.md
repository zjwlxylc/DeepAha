# 单位组独立身份与当前来源关联

状态 IN_PROGRESS，承接公告继承快照 PR #23，属于既定顺序第 3 项的第一部分。先建立机会子项组的独立身份与来源关联，再接组级事实、规则和范围例外；本批不改变资格计算、完整范围批准或 Word 核验状态。

身份底座已由 PR #24 合并，来源关联、新私有契约与后端 API 已 IMPLEMENTED 并完成本地定向验证，见 `docs/development/2026-09-10-group-source-bindings.md`；管理页面仍为 PLANNED，单独实现和验收。

当前 WMA `kind=unit` 表示子项组，`kind=position` 才映射现有 POSITION。单位组不得借用任一岗位的 ID，也不能合并为公告级事实目标。内部 OpportunityUnit 可新增 GROUP 类型以复用稳定 ID、版本及来源包关联；新增私有 `group-identity/1.0.0` 契约承载 GROUP，旧 V08 枚举、导出 Schema、绑定的 positions、已存事实准备和 v2 快照保持原义。GROUP 仅是范围与来源身份，不能作为可申请岗位或最终资格结果公开。

类型边界先落地：内部 UnitService 和数据库支持新 GROUP；旧 singleton split 和 merge 路径拒绝 GROUP 参与，数据库拒绝 GROUP 与其他 kind 互相转换及 GROUP 进入旧 lineage，保留原五类已有行为。新契约不能把 GROUP 伪装为 V08 单元；测试同时证明旧契约拒绝 GROUP。

来源关联另行追加保存，绑定当前 investigation binding、官方来源包、机会版本、WMA group entity 和实际已登记的岗位成员。客户端不能自由传入一个成员子集来缩小范围；服务从冻结交付枚举该组全部子项，逐项关联实际当前岗位身份，未完成登记的子项明确保留为未处理或阻塞登记。分组身份登记不等于批准 WMA 分组含义，不产生 VerifiedFact 或适用性批准。具体接口及成员未登记状态在实现该关联前按既有身份流确定。

稳定键在机会内部唯一，不能按同名自动归并；跨任务、跨机会、别组或陈旧岗位版本一律拒绝。当前绑定变化时旧记录保留且不能作为当前来源使用；需要重新关联时沿用同一组身份并追加版本，不能反复创建同名新组。来源、权限和原件每次读取及重试都重新核验。

验收顺序：先以真实 PG 失败样本验证 GROUP 创建、旧契约隔离、混合合并/拆分拒绝和 SQL 类型/lineage 防护；再验证完整成员分母、稳定身份、绑定更正、权限撤销、并发与幂等、私有 API 和桌面优先管理入口。原五场景 v2 回放保持不变，未知与未核验不转为通过。每个可独立验收的部分单独集成，不同时实现组级事实、范围例外和完整资格放行。

来源关联的具体实现：使用私有 `group-identity/1.0.0`，范围固定 `GROUP_SOURCE_ASSOCIATION_ONLY`。预览以当前 binding 和 raw group entity 为输入，返回服务器重建的完整 source 与 source_hash。保存只接收 entity_id 和 expected_source_hash，不能传入组 UUID 或岗位成员列表。独立的追加记录关联当前 binding、原组、GROUP Unit/Version、完整来源及其摘要、操作者和时间；不修改原 InvestigationBinding。数据库校验真实来源、组身份与完整成员，读取每次重新校验证据、授权、来源政策和当前身份。

源成员按原组 positions 的完整顺序逐项保留：有当前岗位绑定标为 BOUND，否则标为 UNPROCESSED；空组单独标为 NO_MEMBERS。它们只描述身份关联，不代表条件覆盖或资格完成。预览不能从客户端子集构建。内部组键由 task ID 和 raw group entity ID 的确定性摘要生成并加 group 命名空间，原编号及名称保留在来源对象内，避免同名自动归并。

同一 binding/group/source 的保存及丢失回执重试复用记录；重试仍重验当前来源。binding 更正后旧记录拒绝作为当前来源读取，重新关联保留同一 GROUP ID 并追加版本。组的机会归属、原 entity 或外部变更的版本指针不自动改绑。先以纯成员分母测试和真实 PG 追加历史测试完成服务，再接私有 API 与桌面管理页面；上述步骤不改变既定组事实与范围例外的后续顺序。
