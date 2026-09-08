# 调查结果身份登记与字段审核接入

状态：IN_PROGRESS。基线：PR #13 / main fcd1205；此前通用证据链工程已合并，不代表真实发布资格通过。

步骤 1 已 IMPLEMENTED，经完整本地回归和候选 CI #82（9/9）后随 PR #14 合并至 main 757fb3c，主线 CI #83 success。步骤 2 已 IMPLEMENTED，候选 CI #84（9/9）通过，PR #15 合并为 c97b1b8。字段值映射与证据回放分离；候选准备关联不可变机械核验回执，并在写入及人工决定前重新核对当前原件、解析与核验版本。完整记录见 `docs/development/2026-09-08-investigation-field-review.md`。

## 顺序和边界

1. 接入经人工登记的内部 Opportunity 和岗位身份，复用现有身份解析、原件、Document、冻结来源集合和调查归属回执。登记、来源集合、岗位和回执在同一事务内提交；失败全部回滚。重复请求返回原回执；旧版本、重复身份和失效审核权限必须拒绝。
2. 字段映射与审核复用通用 Reader / Verifier / 持久化证据锚点；旧开发分支仅作为行为和测试参考，不引入其按格式另写的引文比较器。准备记录须绑定实际解析和核验版本，不能以旧缓存掩盖证据变化。
3. 按可独立验收的批次验证和合并；后续规则、资格与个人行动链另行顺序接入。

身份登记保持 INTERNAL / UNKNOWN / PENDING，不产生 VerifiedFact、公开发布或自动资格判断。机器核验、内部收件批准、身份关联和独立字段审核分别记录。

不调用 WMA，不修改 V3 Prompt、WMA 模型配置、冻结 Schema、Candidate Facts、原始 quote / locator / artifact。冻结案例继续保持 94 PASS / 0 FAIL / 30 UNVERIFIED，Delivery UNVERIFIED。

## 验证

- 注册真实 PostgreSQL 回归覆盖幂等、并发、完整回滚、重复身份、当前版本和当前审核权限；解析器仍采用主线通用 Reader。
- API 和浏览器审核流程覆盖失败、重试与回执，保留表单内容及同一请求的幂等键。
- 后续字段准备覆盖完整分母、无法核验和独立人工审批，不将 UNVERIFIED 算作 PASS。
- 必要后端回归、静态检查、前端测试与构建；候选提交的远端 CI 全绿后集成。
