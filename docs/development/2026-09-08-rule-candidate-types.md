# 规则候选与编译器的字段类型一致性

规则接入前复核发现：现有候选生成器对专业代码、户籍、毕业状态使用 IN 运算时，将字段类型写成 STRING_SET；当前字段注册表要求三者均为 STRING。由候选进入真实编译器后，三项实际复现 TYPE_MISMATCH。IN 的允许值仍是列表，列表不改变被比较字段自身的类型。

最小修复仅将三项候选的 value_type 改为 STRING；证书集合的 CONTAINS_ALL 保持 STRING_SET。新候选派生版本与 producer_identity 升为 1.0.1，已有候选、审核决定与规则集保留，不自动改写或重新批准。此修复不扩大字段注册表，不修改资格引擎、Prompt 或 WMA 契约，也不直接发布任何规则。

验证：

- 六类条件（学历、专业、户籍、毕业状态、证书、年龄）从候选进入实际编译器与资格引擎，分别检查符合、官方冲突和画像缺失，保留证据引用。修复前三项 TYPE_MISMATCH，修复后全部通过。
- 本地审核、规则、资格和契约回归：231 passed；mypy Linux / Windows 均通过（427 source files）。
- PostgreSQL 审核与发布边界回归：5 passed，含上述三个类型加学历的完整独立审核、重复请求、候选版本及审计记录验证；不代表真实人工验收。
- Ruff 检查与格式通过；独立复核未发现 P2+，另运行 24 项纯测试通过。
- 相关测试：`backend/tests/local_human_test/test_rule_compilation.py`、`backend/tests/local_human_test/test_review.py`、`backend/tests/integration/test_local_human_test_review_publication.py`。

下一步仍是独立规则审核与精确岗位资格接入。全部条件、共同条件适用范围、例外和未处理项的覆盖审查应单独保留；单条规则编译通过不能证明一个岗位可以确定地作出资格结论。

集成已完成：PR #16 的候选 `23f88eb14205c9f491d206a6ebba24b8e60411b5` 在 CI #86（run 34228605773）九项均通过，合并提交为 `0add01de54669f521c83b2d7465d04af62a6e05a`。候选及合并代码树均为 `617c1e30a497ec4d637f4f1093616e671b071f54`。证据见 `evidence/2026-09-08-rule-candidate-types-ci.json`；此工程结论不改变 Release Qualification。
