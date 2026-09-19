# 03｜SG1 可行动机会粒度：实施计划

**Goal:** 让“用户可独立行动的岗位/赛道/项目分项”成为总览、收藏、提醒、资格和反馈的基本单位，同时保留 Root 公告作为审核与证据父实体。

**Architecture:** 保持当前整体审核和 Root Publication；新增轻量 Unit Identity 与 Catalog Target 读模型。通过一次整体决定后，根据 Root + Unit 结构物化多个 Catalog Target。用户状态迁移到 Target，父公告不再是有子单元时的默认列表项。

**Tech Stack:** 当前 FastAPI / SQLAlchemy / SQLite+PostgreSQL / 原生 ES Modules；不更换框架。

**Spec:** `02_ACTIONABLE_OPPORTUNITY_GRANULARITY_SPEC.md`

## Global Constraints

- 不恢复旧 Provider 调查、方法认证、逐字段事实审批和规则批准作为总览前置。
- WMA 输出视为不可信候选；Agent 不批准正式事实或资格。
- 一次整体 APPROVE 仍然是审核唯一人工收录决定。
- 不删除/回滚现有用户数据；迁移必须 additive + backup-first。
- 不把 GROUP 当行动目标。
- 不以标题相似度自动合并 unit。
- 不把“本次返回未出现旧岗位”自动解释为岗位撤回。
- 不在 SG1 接 AI 匹配、支付、外部通知或大规模重写前端。

---

## Task 1：先建立新的失败契约

**Files:**
- Create: `backend/tests/product/test_actionable_granularity.py`
- Extend: `backend/tests/product/test_contract.py`
- Extend: `web/tests` 或 `tests/e2e` 中当前产品目标验证

**必须先失败的测试：**

```python
# 语义示例，Codex按当前fixture接口实现等价测试
assert catalog_total_for(one_notice_with_two_positions) == 2
assert catalog_titles == {"工程研究助理", "技术项目管理员"}
assert no_catalog_card_named("城市工程研究院·青年人才引进")
```

同时建立：

- GROUP 不出卡；
- singleton fallback；
- 两个岗位收藏相互独立；
- Unit public id 跨版本稳定；
- 100 岗位分页；
- root-only 老数据兼容。

**出口：** 红测失败原因必须明确是当前 root-only catalog 行为，而不是 fixture/环境错误。

---

## Task 2：建立 additive schema v2

**Files:**
- Modify: `backend/src/deepaha/product/models.py`
- Modify: `backend/src/deepaha/product/db.py`
- Modify/Create: `backend/src/deepaha/product/upgrade.py` / `migrations/product/`
- Test: 新增 SQLite upgrade + 空库初始化 + 重复升级测试

**新增核心对象：**

- `ProductOpportunityUnit`
- `ProductCatalogTarget`
- target-scoped user state（可新建 v2 表，不要求危险地原地改旧 unique constraint）

**迁移要求：**

- 空库可直接初始化 v2；
- rc2 schema v1 能备份后升级；
- 重复升级幂等；
- 旧 Source/Opportunity/Publication/Decision/Account 保留；
- 不静默把有多子项的旧 root 收藏映射成任一岗位。

**出口：** migration 测试通过；旧 v1 数据抽样哈希/计数不变。

---

## Task 3：把 unit 身份解析从展示 JSON 中抽成独立服务

**Files:**
- Create: `backend/src/deepaha/product/granularity.py`
- Create: `backend/src/deepaha/product/unit_identity.py`
- Modify: `adapter.py`

**接口建议：**

```text
resolve_units(root_item) -> UnitGraph
resolve_actionable_targets(unit_graph) -> list[ActionableTargetSeed]
upsert_unit_identities(session, opportunity_id, revision_id, seeds) -> UnitIdentityMap
```

要求：

- 保留 WMA 给出的 id/code/path；
- path-aware identity；
- GROUP 只做 scope；
- unknown kind 安全回退；
- 弱身份明确标记；
- 不做跨标题相似度自动合并。

**出口：** 纯函数单元测试覆盖 nested group/position、track、region variant、singleton。

---

## Task 4：整体批准时物化 Catalog Targets

**Files:**
- Create: `backend/src/deepaha/product/catalog_projection.py`
- Modify: `intake.py`
- Modify: `catalog.py`

**批准事务语义：**

```text
APPROVE revision
  → upsert root Opportunity identity
  → upsert stable Unit identities
  → supersede旧root publication
  → create root Publication
  → materialize N Catalog Targets
  → tick catalog_revision once
  → return receipt
```

回执扩展：

```json
{
  "opportunity_public_ids": ["opp_..."],
  "catalog_target_ids": ["unit_...", "unit_..."]
}
```

保留旧 `public_ids` 一段兼容期，但新 UI 不应再把它解释成“总览卡片 id”。

**出口：** 1 公告 2 岗位一次 APPROVE 后 catalog=2；只有一个 Decision。

---

## Task 5：重写 Catalog API 为 target-first

**Files:**
- Modify: `catalog.py`
- Modify: `api.py`

要求：

- `/api/catalog` 列出 Catalog Target；
- `/api/catalog/{id}` 支持 `unit_` 与兼容 root singleton；
- 增加 root announcement read endpoint；
- 搜索包括 unit own + applicable ancestor text；
- target detail 返回 sibling summary；
- 50/20 现有分页上限继续保留；
- catalog read_version 继续保护更新期间分页一致性。

**出口：** API 契约测试覆盖 100/1000 unit，响应有界。

---

## Task 6：用户状态迁到 target 粒度

**Files:**
- Modify/Create models for target action/feedback/notice
- Modify: `personal.py`
- Modify: `api.py`

要求：

- 保存 A01 不保存 A02；
- reminder 绑定 target 当前 publication；
- `fit(unit_id)` 返回该 unit 的条件 + ancestor applicable fields；
- recommendation 先仍用当前简单相关性算法，但候选单位改为 target；
- root-only 机会保持兼容；
- old multi-unit root action 不自动猜具体 unit。

**出口：** per-user / per-unit 隔离测试通过。

---

## Task 7：手机端从“公告卡”改成“行动卡”

**Files:**
- Modify: `web/public/product/core.js`
- Modify: `web/public/product/user.js`
- Modify: `product.css` only where necessary

卡片：

- 主标题：unit title；
- 次标题：parent announcement / issuer；
- position code / track / tier；
- 地区；
- 当前可确定行动时间；
- 关键备注；
- 不显示“包含 N 个岗位”作为主要产品价值。

详情：

- unit own fields；
- 公告共同条件分区；
- evidence；
- siblings；
- parent announcement；
- unit-scoped 收藏/提醒/反馈。

**出口：** 360/390/430 px 无横向溢出，目标卡片第一屏明确是具体岗位/赛道。

---

## Task 8：审核端保持“一次决定”，但展示真实收录数量

**Files:**
- Modify: `web/public/product/workbench.js`
- Modify review API response only as necessary

审核首页/详情显示：

```text
公告：1
行动目标：126
预计进入总览：124
局部排除：2
备注：17
```

允许按 unit 快速定位，但不增加 126 个批准按钮。

APPROVE 后展示 target 列表而不是只给一个父公告链接。

**出口：** 审核负担仍是 1 次整体决定。

---

## Task 9：真实 WMA 回放与 Producer Contract 检查

Codex 必须在本地找到一份当前实际 WMA 返回（优先现有数据目录，只读复制到隔离测试目录）。如果真实返回已经有 position/unit 层级，记录并直接验证；如果没有：

- 不在消费端凭文本猜 100 个岗位；
- 输出 `WMA_OUTPUT_GRANULARITY_GAP`；
- 给出最小 Schema / system prompt delta，要求 Agent 明确返回 root + units + stable keys；
- 不擅自修改线上已发布 Agent，除非当前任务环境已明确授权。

真实验收表至少记录：

```text
WMA run id
根公告数
原始 unit/position 数
DeepAha resolved unit 数
Catalog target 数
局部排除数
总览实际可浏览数
```

**出口：** 至少一个真实多岗位包能够“岗位级浏览”；否则 SG1 不得 PASS。

---

## Task 10：回归、文档与停止线

执行：

```text
backend/tests/product
web product checks
new target-level e2e/browser checks
migration/backup test
```

并新增：

`docs/development/SG1_ACTIONABLE_GRANULARITY_DELIVERY.md`

最终状态只能是：

- `SG1_PASS`
- `SG1_CONDITIONAL_PASS`（仅外部 WMA producer contract 尚需人工发布/实测）
- `SG1_FAIL`

**不得在同一任务继续 SG2。**
