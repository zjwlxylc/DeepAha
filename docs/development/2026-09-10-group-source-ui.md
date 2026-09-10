# 单位组来源管理入口

状态 IMPLEMENTED，PR #26 已合并为 `f8eb21afd7b62e45625310af897a9faa12801a53`。候选 CI #107 九项通过，合并与候选同树，主线 CI #108 成功；证据见 `evidence/2026-09-10-group-source-ui-ci.json`。后端 PR #25 已合并为 `ee96b8a2d2b7bc49ca330e532ae9444584c50ffa`，候选 CI #105 九项通过，合并与候选同树，主线 CI #106 成功；证据见 `evidence/2026-09-10-group-source-bindings-ci.json`。

本批为既有 `group-identity/1.0.0` 私有接口接入桌面优先管理页面。当前已批准且来源冻结的调查任务可按原单位组进入预览；页面保留原组全部成员与顺序，显示 BOUND / UNPROCESSED，空组明确显示 NO_MEMBERS。组登记只记录来源与身份，不生成事实、规则或资格批准。

预览地址为 `/review/investigations/{taskId}/group-source?entity_id={rawEntityId}`；已登记地址为 `/review/investigations/{taskId}/group-bindings/{recordId}`。两者强制动态读取。服务端动作将来源与当前任务、机会/绑定/来源包版本、完整原组及实际岗位成员逐项核对，拒绝错组、子集、乱序和状态误报。保存只发送 entity_id 和预览摘要，返回后再读具体回执；登记回执丢失时仅允许重试同一摘要，过期或权限拒绝后隐藏旧内容，不将旧数据继续展示为当前记录。

沿用审核布局，桌面成员并排，窄屏自然换行。用户首页、公开入口、资格计算、后端、冻结 WMA Prompt/Schema、原件和 Evidence Gate 均不改变。

验证：55 项相关测试通过（32 项新增，23 项已有任务页面回归），类型检查及 15 文件定向 ESLint 通过。新增路由完成一次当前生产构建，用于浏览器验证；未重复整站 248 项测试。桌面 1280×900 与手机 390×844 的 12 项定向浏览器测试通过，覆盖完整成员、丢失回执、明确重试、登记地址刷新、来源更正后旧记录失效、稳定组身份及权限撤销。已登记页测试先等待真实 href 导航完成，再刷新。桌面和手机预览、已登记及失效状态共 6 张截图已检查，无水平溢出，证据在 `evidence/2026-09-10-group-source-ui-validation.json` 及同名前缀截图目录。

独立只读复核未发现可复现 P1/P2；验证由实际定向测试、构建与截图检查支持，不代表独立真人验收。

全部浏览器数据与审核账号为合成工程场景。真实案例仍为 94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED，整体资格 UNCERTAIN。未调用 WMA。

后续已进入组级事实后端，见 `2026-09-10-group-fact-review.md`。组规则继承仍是后续独立任务；不包括自动批准完整范围、Word 机械核验放行或个人资格发布。
