# GROUP 规则到 POSITION 的只读上下文

内部服务 IMPLEMENTED；尚未提供 API、页面或适用裁决写入。分支 `codex/group-rule-applicability`，基于 PR #32 已验证同树合并 `2fc37ee3d8fab08a93e9a730a933ea7f80cb68af`。本批不宣称整个 GROUP 适用链路完成。

`read_group_rule_applicability` 重建当前岗位计划与实际 GROUP 规则审核记录，验证同一 task、delivery、binding、check、source bundle、机会及版本。来源组必须在原始成员关系中明确包含该岗位，且成员绑定精确匹配当前 POSITION 与版本。GROUP 实际决定必须为 APPROVE；同一机会不构成成员关系，也不构成适用批准。

上下文采用 `group-rule-applicability-context/1.0.0` 严格字段契约及摘要；返回完整 GROUP 审核记录，保留未处理字段、未绑定成员和岗位计划原有不确定性。证据按当前 DIRECT_WMA 原件的 reader block 分页返回。读取证据后清除 ORM 缓存并再次重建上下文，拒绝读取过程中出现的策略变化。输出固定 `GROUP_APPLICABILITY_CONTEXT_ONLY`、`UNDECIDED`，无数据库写入，不改变旧 announcement applicability 路径。

验证：新增上下文 13 项 PostgreSQL 集成用例通过，原公告适用与岗位快照 46 项回归通过，总计 59。前 57 项见 `evidence/2026-09-10-group-applicability-context-tests.xml`；独立审阅后补入的真实非成员与完整成员分母 2 项见 `evidence/2026-09-10-group-applicability-membership-tests.xml`。3 个 Python 文件的 Ruff 与 mypy 通过。仅定向验证，没有重复整站前端测试或生产构建。测试使用合成材料、账号和批准，不代表真实人工验收。

实际冻结样本仍为 124 引用：94 PASS / 0 FAIL / 30 Word UNVERIFIED；Delivery UNVERIFIED，整体资格 UNCERTAIN。没有 WMA 调用、外部下载、Prompt 或原始 Candidate Facts 修改。

## 恢复顺序

1. 当前为本地提交安全点；本批尚未创建 PR 或合并。保留既有 `backend/.pytest-unit-replay/` 与 `web/output/`，不清理它们。
2. 下一批以中档接入此只读上下文的私有 GET API、严格响应契约、桌面管理页入口与过期/权限/失败隐藏行为。继续当前工作区和任务窗口；只有新增影响才重跑相关测试。
3. 之后再独立实现 GROUP 适用决定保存：新持久化关系、实际批准绑定、官方引文精确核对、幂等/前序 CAS、不可变审计及异常路径。不得放宽旧公告表的外键或来源约束。该步骤涉及跨层写入与并发边界，应重新评估是否切高。
4. APPLIES 决定也不自动形成资格放行；例外、冲突和继承计划必须另有明确契约与回放。
