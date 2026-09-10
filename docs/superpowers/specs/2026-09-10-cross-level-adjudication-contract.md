# 跨层条件关系裁决契约 v1

## 目标与边界

承接 PR #39 的完整只读 CrossLevelReview。实现独立版本 `cross-level-adjudication/1.0.0` 的提案、审核历史及确定性回放；不增加数据库写入、HTTP 入口、页面控件或资格编译。现有 v2、Evidence Gate、原始事实与全文摘要不变。

选择“完整来源快照上的显式关系提案”，而非字段同名自动 AND 或岗位条件自动覆盖公告。按全部同名字段统一裁决会把不相干条件混在一起，也遗漏不同字段之间的关联；任意条件子集可以提出关系，但完整 manifest 永远保留，子集获批不等于全部条件审核完成。

## 关系语义

- `CUMULATIVE`：所列条件同时成立才满足这组要求，只记录人工解释，不合并数值、不执行 AND。
- `EXCEPTION`：官方材料明确给出针对当前精确岗位版本的例外，`displaced_condition_ids` 指明在该关系中被例外取代的条件；其余所选条件共同承载例外。必须是非空真子集，不能隐式按层级或发布时间选择。部分、依赖个人状态或尚不明确的例外以 `UNRESOLVED` 保留；后续可执行条件表达式需独立版本设计。
- `CONFLICT`：确认这些官方材料尚有冲突，保留所有原文，批准此提案只确认冲突存在，不选赢家。
- `UNRESOLVED`：关系尚不能确定，不得 APPROVE；可要求继续裁决或拒绝提案。事实本身 UNKNOWN 与 UNPROCESSED 保持原状态，关系状态不替换事实状态。

所选条件至少两条，至少跨两个 scope；允许不同 field_name。按 manifest 顺序提供唯一 condition_id；摘要绑定整个 CrossLevelReview，不能借同名字段、索引或相同文本迁移到其他实体/岗位。已 EXCLUDED、UNRESOLVED 或非 KNOWN 的 LOCAL 条件不能进入前三种明确关系；可进入 UNRESOLVED 诊断。INHERITED 条件的冻结基础状态可能仍为 UNPROCESSED，使用已通过源投影校验的当前范围决定，而不重写基础状态。

## 提案、证据与审核

提案不可变：proposal_id、producer_id、created_at、完整 source_review 及其摘要、condition_ids、relation、displaced_condition_ids、reason、evidence。新解释、新条件选择或新来源须创建新提案，不能改写旧提案。v1 不生成“当前生效规则集”，并行提案相互矛盾也不自动执行。

证据沿用现有审核的 member/block/quote、document/material/source_url、evidence_ref_id、block_hash、binding_hash、locator，并新增用途与条件绑定。`CONDITION` 用途覆盖每一个所选条件；至少一个 `RELATION` 引文绑定整个条件集合，承载同时满足、例外或冲突的理由。重复项、空白 quote、缺少定位、非所选条件及漏条件拒绝。UNRESOLVED 可以无证据；给出的证据仍须合法。

契约仅验证引用结构和绑定一致性。官方身份、原件、原文 quote、block_hash、材料所属任务/来源包均由后续受信服务在事务中重载验证，禁止接收浏览器自报的 bound evidence；Python 对象或哈希自洽不是已完成官方核验。原始引文、定位与全文不做额外规范化。

审核记录追加保存：decision_id、proposal_id、proposal_hash、sequence、previous_decision_id、reviewer_id、created_at、APPROVE/REJECT/NEEDS_ADJUDICATION、reason。禁止 producer 自审；所有审核者身份必须来自认证 principal。契约的不同 UUID 仅作关系约束，不能证明独立真人身份。审核同一提案的修订必须连续，时间非递减、不得早于提案或超出独立提供的回放时钟；记录 ID 唯一，latest 从完整历史计算，不接收客户端选择。

## 回放与失效

离线包包含完整提案与完整审核历史；另传独立保存的整个包摘要，防止重算内部哈希后删尾、重写审核者或伪造批准。包自身摘要不能充当信任根。当前来源由可信调用方另行重建；它必须与提案属于同一个 task/plan，其他目标直接拒绝。同目标任意来源/批准/范围历史改变，整个 source_review 摘要变化即标 `STALE`，旧批准不作为当前批准。v1 采用保守全快照失效，不复用兄弟条件历史前缀。

回放永远返回完整原始 snapshot、完整所选及未选 condition_id、最新记录和审查状态，并保留全部原 blockers，追加 REVIEW_ONLY；CONFLICT 与 STALE 各有明确 blocker。固定 executable=false、overall_qualification=UNCERTAIN。不移除被例外取代的原行，不把一组提案获批表述为覆盖完成。历史回放不认证当前用户、不能证明当前来源仍开放或权限仍有效。

## 本批验收与后续接入

纯契约测试覆盖真实合成 API 导出的全层输入、四种语义、定向例外、不同字段、漏条件、跨目标/摘要变化、空白/错绑证据、自审、篡改/删尾历史、修订/时间、输入不变与固定资格。重跑关联 cross-level/继承契约测试；不因纯 Python 新模块重跑前端构建。

后续独立批次：持久化不可变提案及追加审核记录；事务内重载当前 CrossLevelReview 与官方 block，锁定任务/提案和认证账号，保存前再次重建；幂等键绑定 principal/目标，旧 previous 冲突，变更/撤权拒绝；私有 API 用身份与预期摘要接收请求，不接收 source_review/producer/reviewer/bound evidence。用实际 PostgreSQL 验证后再接桌面审核页。资格编译仍是另一个阶段，需解决相互重叠提案、条件性例外、完整覆盖和执行冲突，不能直接消费本契约当可执行计划。
