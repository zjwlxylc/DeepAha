# 单位组字段事实独立审核后端

状态 IMPLEMENTED，本地定向验证与只读复核通过，候选 CI 尚待执行完成。分支 `codex/group-fact-review`，基于 PR #26 合并后的 main，工作区为 `D:\DeepAha\.worktrees\integration-wma-evidence`。

组来源登记现在可进入独立事实准备：服务器保留全部原始组字段、不可处理项及其他层级的排除索引，以精确 GROUP Unit/Version 持久化候选。准备本身不批准事实；独立审核人逐字段给出 APPROVE / REJECT / UNKNOWN / NEEDS_ADJUDICATION，全部可处理候选终局裁决后才能保存事实集。未知只能保存 UNKNOWN。旧公告/岗位事实桥、旧 V08 UnitKind 与规则入口保持原义，组事实不冒充岗位事实。

新增私有接口（前缀 `/api/v1/local-human-test/investigations/{task_id}`）：

- `POST /group-bindings/{group_binding_id}/facts`：按当前来源摘要和证据回执准备。
- `GET /group-facts/{preparation_id}`：读取并重新验证已保存记录。
- `POST /group-facts/{preparation_id}/decisions`：独立字段裁决，要求 Idempotency-Key。
- `POST /group-facts/{preparation_id}/promotions`：保存事实集，要求 Idempotency-Key。

请求拒绝额外字段、非法枚举与调用者提供的事实值。读取和返回均 private/no-store。准备、读取、裁决、晋升及同键重试重新验证权限、原件字节、来源策略、当前身份/版本和证据映射。迁移 0047 新增独立准备与追加动作表；数据库约束保持原始分母、关联、裁决及审计记录一致。非空历史拒绝降级。

评审发现并以失败测试复现两处缺口，已补齐：实际事实值不能与获批候选发生偏差；准备后追加合法但非本字段的证据不能继续获得有效回执。统一的 SQL materialization 校验同时用于读取与动作写入，核对实际候选值、状态、精确证据集合、事实值、依赖指纹及时间。未来候选、决定或事实时间均被拒绝。独立复核未发现剩余 P1/P2；这不代表真实人工事实批准。

本地验证合计 109 个不同测试通过：新增 PostgreSQL/迁移 34；已有调查事实与组来源 36；P9B 持久化 3；API/字段映射/事实链 scope 36。按受影响范围分批运行；新追加用例只定向补跑，复用同代码已通过结果。P9B 首次两项因本地 S3 未配置而未执行，恢复已有 Moto 测试容器后该文件 3 项通过。Ruff 9 文件、mypy Linux 7 文件通过。未重复前端整站测试或生产构建。记录见 `evidence/2026-09-10-group-fact-review-validation.json`。

所有数据为合成工程场景。没有 WMA 调用、官方原件下载、Prompt/冻结 Schema/原始 CandidateFacts 修改。真实案例仍为 94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED，整体资格 UNCERTAIN。

安全恢复点：本批提交并创建 PR 后，可切到“中”档。下一步先检查精确候选 CI，全部通过后合并并核对同树，再为这四个接口接入桌面优先的组事实审核页面，覆盖已保存地址、刷新、过期与错误状态。组规则目标及继承/例外语义须后续单独设计；若进入这类高风险决策，先在安全节点提示切回“高”。当前不扩大到组规则、资格放行或发布。
