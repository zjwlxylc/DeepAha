# 可信条件快照到合成画像的回放

真实 PostgreSQL 中的调查、原件、身份、字段事实、独立规则记录和受信快照已经与既有资格内核连接验证。本批仅增加集成测试及可复查证据，未改变生产契约、API、快照或计算行为。

8 项新增集成测试通过（最终 17.04 秒）。测试先持久化并重读 `synthetic=true` 的 0.4.0 画像；每次经 `load_unit_plan` 重建当前计划后再计算。符合学历、学历冲突和学历缺失分别得到 `SATISFIED / CONFLICT / UNKNOWN`，原始规则汇总分别为 `ELIGIBLE / INELIGIBLE / UNCERTAIN`；最终全部为 `UNCERTAIN`。同一输入完整输出及摘要可重复，五元目标中的任意一项变化均拒绝比较。

未知公告条件不会被完整画像补成满足。混合条件样本保留 9 个来源字段的分母、7 个当前范围条件及 2 个其他目标的排除记录，未定位、拒绝、未知条件及原备注仍出现在快照和计算阻塞中。证据为该样本的 8 PASS / 0 FAIL / 1 UNVERIFIED，不能据此推断真实冻结样本已经通过。

初轮 1 failed / 7 passed 的原因是测试把“保留官方引用”误写成“缺少画像字段时仍可声明官方确定性比较”。既有引擎对缺值返回 `FIELD_MISSING`、保留引用、`official_evidence=false`、`deterministic=false`；核对后修正测试，未修改引擎。Ruff、格式、mypy Linux/Windows（445 files）通过。独立审查未发现 P1/P2；独立执行三份共 5 场景的只读重放通过，内存篡改输出、引用、合成标记、场景数量或源码摘要均不能误报通过。独立审查未访问共享数据库或网络。

完整合成输入及输出：

- `evidence/2026-09-08-trusted-unit-profile-replay/persisted-profile-matrix.json`：三种画像。
- `evidence/2026-09-08-trusted-unit-profile-replay/unknown-condition.json`：已调查但未知的官方条件。
- `evidence/2026-09-08-trusted-unit-profile-replay/multi-scope-conditions.json`：多层来源、未定位与拒绝条件。

每份保留完整计划、来源上下文、实际测试数据库关联 ID、画像版本和属性、两个时钟、专业目录与映射、源码摘要及完整结果。`2026-09-08-trusted-unit-profile-replay.py` 只读取这些文件并调用纯内核；已成功重放三份共 5 个场景，逐字段等于已记录结果，零数据库写入、零网络调用。源码摘要只对 checkout 的 CRLF→LF 规范化，未改任何官方原件或引文。

从仓库根目录可执行：

```powershell
$env:PYTHONPATH='backend/src'
backend/.venv/Scripts/python.exe docs/development/evidence/2026-09-08-trusted-unit-profile-replay.py docs/development/evidence/2026-09-08-trusted-unit-profile-replay/persisted-profile-matrix.json docs/development/evidence/2026-09-08-trusted-unit-profile-replay/unknown-condition.json docs/development/evidence/2026-09-08-trusted-unit-profile-replay/multi-scope-conditions.json
```

这些文件只证明历史合成输入可重复计算，不能作为当前数据库准入、真人裁决或发布资格。fixture 的 reviewer 身份只用于测试鉴权路径，所有真实参与者、真人批准及 WMA 调用均为零。冻结 WMA 样本仍为 94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED。

状态 IMPLEMENTED，本地集成及文件重放通过，候选 CI / 合并待完成。下一步审阅公告/单位条件的适用范围与例外记录路径；在其验收前，不解除整体资格的范围阻塞。
