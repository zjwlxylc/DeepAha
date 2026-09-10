# 公告继承条件的受信派生快照

状态 IMPLEMENTED，承接 PR #22；PR #23 已合并，候选 CI #101 九项全部通过且合并同树。验证见 `docs/development/2026-09-09-announcement-inherited-snapshots.md`。只处理既有公告到精确岗位的适用记录，不扩单位组事实、完整范围签署或资格放行。

现有 unit-qualification/2.0.0 保持原义和原字节回放。新契约以已持久化 v2 plan_id 为 base_plan_id，并保留完整 base 快照及其摘要。它是当前来源和适用结果的派生审阅快照，不能提交给 v2 编译器。父级规则及 fact ID 保持公告身份，不伪造或复制成岗位事实；实际新版资格消费留给范围与例外之后的回放批。

新快照必须保留当前来源分母及备注、排除、单位组未知和不可核验项，逐条公告 condition 关联实际 source preparation / fact set / fact / rule candidate / approval / applicability 最新记录。只在来源当前、事实和规则已实际批准且对本确切岗位的最新决定为 APPLIES 时标为 INHERITED；DOES_NOT_APPLY 记录为明确范围排除，并保留实际引文及决定，不等同非资格字段。NEEDS_ADJUDICATION、没有决定、没有已批准规则、未处理和证据不足分别保留未决原因，不因客户端漏传来源而消失。

服务自行枚举当前全部公告来源和决定，客户端只提供 base_plan_id；不存在由调用方选择一组 APPLIES 的输入开关。dependency hash 包含 base 身份/摘要、完整当前公告来源及 null/待裁决/排除/适用的最新记录。新决定、规则准备或事实集变化均使旧派生结果不能作为当前输入，原记录完整保留用于历史审计。读取重新验证 base、原件和授权，再重建比较完整新快照；相同依赖与请求重试返回同一记录。

独立 append-only 表以 base_plan_id 和依赖摘要定位版本；引用的 applicability 始终指向 base v2，避免派生快照与适用历史相互循环。每次 materialize 使用 task 锁，记录 parent source 和每个 latest decision；唯一约束确保并发不会产生重复内容。SQL 保护真实关联、当前权限、摘要及不可变历史，有记录不得降级删除；可信读取仍承担完整重建，不能只检查自报 hash。

私有 API 延续 private/no-store 和实际授权，页面在基础快照旁提供派生查看入口，分别展示本岗位、继承公告、公告排除、待裁决和其余未处理范围。旧派生快照不可用时隐藏内容，提示从当前基础快照重建；整体 UNCERTAIN 不解除。

接口为读取当前输入 `GET /{task}/unit-plans/{base}/announcement-snapshot-input`、提交期望依赖摘要 `POST /{task}/unit-plans/{base}/announcement-snapshots`、按 ID 受信读取 `GET /{task}/announcement-snapshots/{id}`。第一项返回 `dependencies`、`dependencies_hash` 和当前派生内容；POST 只接收 `expected_dependencies_hash`，与实际输入不同即拒绝。派生内容明确 `scope=DERIVED_SCOPE_SNAPSHOT_ONLY`，契约 `investigation-announcement-snapshot/1.0.0`，完整 `base_v2`、`announcement_conditions` 和剩余边界。每行保留 source condition、source fact / rule / approval / applicability 及 disposition/reasons；纯内核 v2 不接受此 wrapper。

来源整组未终局、没有规则准备或被拒绝的条件仍保留。仅对具有当前已批准规则的分支复用严格 applicability 验证；不得吞掉其 409 并伪装成不存在来源。新表唯一键为 `(base_plan_id, contract_version, adapter_version, dependencies_hash)`；摘要明确包括 null 和每个非适用决定，不因相同 outcome 而忽略新决定 ID、证据或理由。

验收：旧 v2 计划及原有画像回放逐字段不变；公告同规则适用于不同岗位时来源身份不变而目标决定分离；APPLIES/排除/待裁决/null/没有源规则的覆盖；更正后旧快照拒读并生成新 ID，相同状态幂等；不同岗位/来源/事实集/证据检查/版本不能串用；权限撤销及原件篡改拒绝；真实 PG 的追加/唯一键/禁止覆盖和有历史降级；私有 API、组件与桌面/手机浏览器；所有数据为合成工程夹具。
