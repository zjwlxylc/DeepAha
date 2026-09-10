# 单位组独立身份底座

状态 IMPLEMENTED，本地定向验证通过，候选集成待完成。这是既定范围集成第 3 项的第一小批：内部 `OpportunityUnit` 支持 GROUP，复用稳定 ID、来源包和追加版本；组级来源关联、私有 `group-identity/1.0.0` 交付契约及管理页面在下一批实现。本批没有启用组级事实、规则、范围批准或个人资格。

旧 V08 Unit 枚举与所有导出 Schema 不变，仍拒绝 GROUP。现有岗位候选查询不会列出 GROUP，直接拿组 ID 绑定岗位也会被拒绝，且不会留下新绑定。组与岗位的同名标签不会自动归并；新组登记接口将使用明确的组键命名空间，保留原来源编号。

服务在修改旧身份前拒绝 GROUP 参与 singleton split、merge、reversal 及 rekey。迁移 `20260910_0045` 扩展内部 kind CHECK，同时禁止 GROUP 与原五种 kind 双向转换。旧 lineage member 插入必须找到精确、已存在且非 GROUP 的 Unit/Version；缺失父身份也拒绝，防止同一 CTE 先插关系、后创建 GROUP 的顺序绕过。有 GROUP 历史时拒绝降级；原五类已有合并及版本行为保留。

实际验证：初始 11 个新增场景因 GROUP 尚未支持或缺少专用边界而失败，随后实现最小改动。最终定向 PG 80 passed，加岗位入口隔离 1 passed，共 81 项且无失败/跳过；其中本批新增 23 项。旧 V08 契约 13 passed，含新增 GROUP 拒绝断言及导出文件字节一致检查。迁移往返、模型差异检查和历史拒降级包含在上述 PG 测试中。7 个受影响 Python 文件 Ruff/格式检查、6 文件 Linux/Windows mypy 通过。独立只读复核未发现剩余 P1/P2。

证据见 `evidence/2026-09-10-group-identity-core-validation.json`。本批仅后端身份底座，复用前批已通过的 UI 证据，没有重复本地整站 248 测试或生产构建。全部为合成工程证据；固定 WMA 案例仍为 94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED，整体资格 UNCERTAIN。
