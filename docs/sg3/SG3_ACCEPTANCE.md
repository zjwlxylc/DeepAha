# SG3 验收门

## Gate C：Currentness

SG3 只有以下条件全部成立才允许人工验收：

1. 单 Target 更正不会污染兄弟 Target；
2. Root/common 条件变化能准确影响后代；
3. 新返回缺失某 Target 不会自动撤回；
4. 明确撤回 Unit 只撤对应 Target；
5. 明确撤回 Root 才撤全部后代；
6. 附件替换只影响真正引用该附件的 Target；
7. 已知过时 deadline 不继续驱动提醒；
8. APPROVE 后产生新 target version，旧版可查；
9. REJECT 不静默恢复已知可能过时的提醒；
10. 历史/compare API 能重建关键 before/after；
11. Target-scoped manual withdraw 不撤兄弟项；
12. Targeted RECHECK 只复查当前目标和受影响字段；
13. SG1 用户真实 106 岗位无解释变化为 0；
14. SG2 多类型契约保持；
15. lifecycle 等内部元数据不作为用户业务字段展示。

## 自动证据

最终交付应包含：

- `backend/tests/product/test_currentness.py`
- `backend/tests/product/test_currentness_api.py`
- `evidence/sg3/api_acceptance.json`
- `evidence/sg3/real_sg1_regression.json`
- `evidence/sg3/product_tests_by_file.txt`
- `evidence/sg3/web_check.txt`
- `evidence/sg3/product_compileall.txt`
- `evidence/sg3/browser_environment.json`

## 人工停止线

只要出现下列任一项，SG3 不通过：

- A01 延期导致 A02 变更/提醒取消；
- “本轮没看到”被系统当成撤回；
- 更正待收录期间仍把旧 deadline 当现行可执行日期；
- 撤回一个岗位导致整份公告所有岗位退出；
- 历史版本被覆盖；
- 用户详情出现内部 lifecycle 技术字段；
- 真实 SG1 106 岗位不再保持。
