# 跨层关系契约实施计划

目标：将关系提案与独立人工审核的边界落实为离线可验证契约，后续服务可按同一契约接入。
设计：`docs/superpowers/specs/2026-09-10-cross-level-adjudication-contract.md`。
技术：现有 Python 3.14、Pydantic、pytest；无新依赖。当前工作区已隔离，沿用授权实施。

1. 新增 `backend/tests/investigations/test_cross_level_adjudication.py`。使用已合并 `web/tests/cross-level-fixture.json` 与 GROUP 正例，覆盖四种语义、例外方向、完整分母、证据用途、独立审核、连续历史、可信摘要和失效。先确认缺失模块导致失败。
2. 新增 `backend/src/deepaha/investigations/cross_level_adjudication.py`。实现 BoundRelationEvidence、RelationProposal、RelationDecision、AdjudicationPackage 及 `replay_adjudication(value, expected_package_hash, current_source_review, as_of)`；不挂 API 或改变编译器。必要时按模块职责拆分。
3. 运行新测试和既有 `test_cross_level_review.py`、`tests/api/test_group_inheritance_contract.py`；Ruff 格式/检查、mypy。检查异常输入与负例真正触发预期验证。独立代码复核后修复并定向复验。
4. 保存验证输出与恢复说明；精确候选 CI 成功才合并。后续数据库与接口接入在明确边界后可中档推进，到安全点交接。
