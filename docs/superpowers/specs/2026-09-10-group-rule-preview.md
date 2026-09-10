# 单位组规则只读预览

本批只实现从组字段审核回执到规则预览的只读接入。既有 `rules._context` 和 `applicability._review_context` 锚定旧公告/岗位准备记录，不能接收新的 GroupFactPreparation；不把 GROUP 伪装为公告或岗位来复用旧入口。

GET `/api/v1/local-human-test/investigations/{task_id}/group-facts/{preparation_id}/rules/preview` 使用现有私有审核权限。在同一事务重新核对任务、精确组身份与版本、来源和原件、候选与事实物化、历史裁决；存在事实集时还要求其当前为 ACTIVE。无事实集可以显示待处理情况，但不生成规则预览。

私有契约 `group-rule-preview/1.0.0` 返回完整 GroupFactRecord、精确 GroupIdentity、逐原始组字段的预览行，以及结果摘要。每一原始组字段保留 source_index，其他层级的排除分母仍保留在完整事实回执中。候选、正式事实与预览 payload 保持独立；只对已保存 KNOWN 事实使用现有确定性 deriver，记录其版本。未知、冲突、拒绝、没有证据的未处理字段和不能执行的元数据均不能产生资格规则。预览不是持久化 RuleCandidate，更不是批准或 applicability 回执。

不创建迁移，不写规则、裁决、继承快照；不新增匹配计算或 full-scope 放行。不修改冻结交付 Schema、原始字段、quote、locator、V3 Prompt 或实际 WMA 样本。实际样本仍为 94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED，整体资格 UNCERTAIN。

验收使用合成审核场景：精确目标、完整分母、KNOWN/UNKNOWN/CONFLICT/拒绝/未处理/元数据分支、稳定重复 GET 无写入、过期组版本和失效事实集拒绝、权限撤销、错误任务与私有 API。READ COMMITTED 下，首次核验和后续取数之间的合法证据追加必须被取数后的最终物化检查拒绝。合成账号只证明工程行为，不是真人批准。

后续按顺序接入桌面优先的只读预览页面，再单独设计和实现持久化组规则候选及独立批准。规则获批也不自动对所有子岗位生效；下一层需精确目标、版本化适用证据和逐项例外裁决。当前小批预览不能替代这些尚未实现的步骤。
