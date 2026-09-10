# 组条件继承的内部只读预览

本批 IMPLEMENTED，本地定向验证通过；独立代码审阅未发现可复现的 P1/P2。精确候选 CI 尚待运行，不代表正式发布资格或可执行继承计划。前置 PR #35 已经通过 CI #125 全部 9 个任务，合并为 `81fd0706eb5b2458aa6deddfe493c68df8552400`，候选与合并树一致。

## 本批行为与边界

内部服务 `preview_group_inheritance` 仅接收任务、岗位快照和审核者。它从冻结实体关系确定父组，逐条核对岗位基础快照中的 EMPLOYER_GROUP 条件与原始组事实，保留整个 `base_v2`。组来源、注册身份、完整成员、事实准备/晋升、规则审核、实际适用历史一起构成依赖及摘要。

只有实际已批准的组规则才读取适用历史。最新 APPLIES 对该条条件产生 INHERIT，DOES_NOT_APPLY 产生 EXCLUDE；待裁决、未决定、未准备、事实未知、事实拒绝、规则拒绝及未处理字段均保留为 UNRESOLVED，并给出不同原因。INHERIT 只表示审核后的作用范围投影，规则仍属于原 GROUP 身份，不成为 POSITION 规则或资格裁决。

每条记录保留原条件、原规则、独立审核和适用决定。所有实际适用记录必须在当前历史中完整出现，否则拒绝返回。读取期间再次重建依赖，来源策略变化会被拒绝；审核账户行锁串行化并发撤权，撤权提交后再次读取必须失败。组版本变化不能复用旧批准和适用决定。

结果含 `dependencies` / `dependencies_hash`、`snapshot` / `snapshot_hash`，版本为 `group-inheritance-preview/1.0.0`，范围为 `GROUP_INHERITANCE_PREVIEW_ONLY`，`overall_qualification` 固定 UNCERTAIN。当前是内部 Python 服务，没有新 API、界面、持久化、迁移或资格编译器改动；未实现跨公告/组/岗位规则的覆盖、冲突裁决与执行。

## 验证

实际 PostgreSQL 定向测试 16 项通过：三种适用决定与追加更正、拒绝/待裁决规则、无写入、未准备事实、未晋升事实、未准备规则、未知/拒绝事实、来源策略读中变化、审核账户锁与撤权、未注册组/空组条件、组版本更新。保留全部条件和整个 base_v2；输出始终 UNCERTAIN。Ruff 格式、Ruff 检查、两份受影响文件 mypy 通过。没有重复整站测试或生产构建。

新增测试最初暴露两个夹具错误：UNKNOWN 必须对应弃答候选，全部拒绝时不能晋升空事实集；已按现有事实契约修正测试输入。权限并发用例原先等待已锁账户，已改成 100ms lock_timeout 验证串行化，再在撤权提交后验证拒绝。业务权限与事实契约没有为测试放宽。

证据为 `evidence/2026-09-10-group-inheritance-preview.xml`、定向边界重测 `evidence/2026-09-10-group-inheritance-preview-edge.xml` 和 `evidence/2026-09-10-group-inheritance-preview-validation.json`。这些是合成数据的工程验证，不是真实人工批准、Gold 评估或 WMA 实测。

## 安全暂停与下一步

沿用 `D:\DeepAha\.worktrees\integration-wma-evidence` 和当前任务窗口。先检查本批 PR 的精确候选全部 CI；只有全部成功才合并并核对树。下一批可用中档实施私有只读 API 与桌面优先展示：先固定严格响应契约，逐一核对完整条件、身份、摘要和实际决定链，再复用审核授权与 private/no-store；页面明确“范围预览，非资格结论”，过期/权限/读取失败时隐藏旧数据。优先定向 API、组件及相关浏览器测试。

若进入跨层级冲突语义、可执行继承计划或持久化版本设计，应重新评估是否需要高档，在开始该依赖工作前保留安全点。中档能否实际减少总 token 还受任务重试与上下文读取影响，不承诺固定比例。

真实样本仍为 124 = 94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED，资格 UNCERTAIN。本批无 WMA、模型或官方下载，没有更改 V3 Prompt、冻结 Candidate Facts、原件或 Evidence Gate。
