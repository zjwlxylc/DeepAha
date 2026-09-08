# 调查候选字段与独立审核接入

实现基线：PR #14 / main `757fb3c0522b2092bbaa402e3e8ea3ea166d783f`。本批实现内部字段准备、逐条独立人工决定与审核事实集保存；规则与资格判断按下一批接入。

## 行为与证据边界

字段清单保留每个原始条目、调查状态、原值、引文、定位与完整分母。只有已关联当前机会或岗位、字段映射受支持且全部引用具有通用核验 PASS 和真实持久证据绑定的条目，才生成 ExtractionCandidate。未支持的字段、未关联目标、未核验引用继续显示为待处理；不会因为其他字段保存成功而消失。

候选准备只做确定性的值映射，不另建 HTML / PDF / Word / Excel 引文比较器。每条引用保留原始 reference、不可变 check_reference，以及实际 DocumentBlock / EvidenceRef 身份。展示的结构位置与完整证据块也由数据库核对，包含未生成 Candidate 的行。

准备、决定与保存均核对当前原件、解析版本、来源归属、机会及岗位版本和核验回执。材料、解析或核验版本变化后拒绝旧操作。机械核验、内部材料批准、身份登记、字段批准分别记录；所有真实事实决定仍由获授权的独立真人负责。

浏览器默认不选批准、原文支持或例外核查。UNKNOWN 候选不能批准为已知事实；NEEDS_ADJUDICATION 保留待裁决记录，后续可追加明确决定，历史不覆盖。最终决定不可重复或重新打开，同一 decision_id 只能对应一个 Action。保存要求当前目标的候选均有明确决定，并至少有一项 APPROVE 或 UNKNOWN；保存得到的部分事实集不表示完整资格结论或公开发布。

响应丢失后的重复提交使用同一表单标识、请求内容与幂等键；服务返回已记录结果。数据库、候选、决定与审核回执在事务中一致提交。新迁移 `20260908_0040` 不修改历史迁移；存在审核历史时拒绝降级删除。

## 通用核验回执版本 2

`investigation-evidence-check/2` 将材料在共同入口按 `(raw_artifact_id, material_id)` 排序，保证首次准备与重放顺序一致。移除输入摘要中的展示性 `evidence_ref_count`：身份归属新增的原件整文件引用不改变 Reader 证据块，不应使字段回放误报过期。实际原件、文档、解析、块、引用及绑定完整性检查保留。旧回执不可变，`evidence-literal/1` 与引文比较规则不变。

## 验证

- PostgreSQL 定向 18 passed：包括反序的两个材料、人工 UNKNOWN、待裁决恢复、重复 Action 拒绝、非 Candidate 证据块篡改拒绝、决定与请求一致性、核验版本变化、不可变准备和历史降级拒绝。共同核验另有 13 项 PostgreSQL 回归，包含只读同回执重放及原件整文件引用不扰动 Reader 输入。
- 独立评审发现并复现排序、待裁决恢复、未生成候选行的块校验和重复决定回执问题。均先建立失败用例再修复；最后定向复核无遗留 P2+。
- 后端非集成：1330 passed / 552 deselected。Ruff 检查及格式通过；mypy Linux / Windows 均通过，426 source files。
- 前端：145 passed / 31 files；typecheck、lint、production build 通过。
- 浏览器：16 passed，桌面 1280×900 与移动 390×844。新字段流程覆盖整理候选、待裁决、明确批准、保存，并在这四次操作各模拟一次响应丢失；11 次 POST 只发生 7 次状态写入（包括前置三步）。逐项确认初始为空，待裁决后可恢复，原文和未知项保持可见，无横向溢出。
- 桌面与手机截图已实际查看：`web/output/playwright/investigations/investigations-reviews-fie-d6055--retries-each-lost-response-{desktop,mobile}/field-review-retry.png` 与 `field-review.png`。均为合成数据，仅验证工程流程。
- 完整 PostgreSQL / S3 回归：549 passed / 3 skipped / 1330 deselected，428.70 秒；Alembic check 无新增迁移操作。空库可从 0039 升级至 0040 并往返；有审核历史时降级被拒绝。
- 候选提交及远端 CI 结果在合并后记录；本地验证证据见 `evidence/2026-09-08-field-review-validation.json`。

测试入口：`backend/tests/integration/test_investigation_facts.py`、`backend/tests/integration/test_investigation_evidence_checks.py`、`backend/tests/investigations/test_field_mapping.py`、`backend/tests/api/test_investigations.py`、`web/tests/investigation-fact-review.test.tsx`、`web/e2e/investigations.spec.ts`。

## 冻结案例与当前限制

对同一批已回收结果与原件离线重放：94 PASS / 0 FAIL / 30 Word UNVERIFIED，Delivery UNVERIFIED；124 条结果逐条相同，六份输入哈希前后一致，临时回放数据库已移除。证据：`evidence/2026-09-08-field-review-receipt-replay.json`。

没有重新运行 WMA，没有修改 V3 Prompt、模型配置、冻结 Schema、原始 Candidate Facts、quote、locator 或 artifact。当前冻结 Schema 仍只接受 CONFIRMED / CONFLICT / INSUFFICIENT / UNKNOWN；界面另行显示系统尚未接入的条目，不能把它们冒充调查后未知。映射器对其他状态的防御处理不代表机器契约已扩展。

未核验的 Word 引用继续保留。工程验证和测试身份不替代真实独立人工批准、Gold 验证或发布资格。本批没有运行规则生成、发布资格、个人推荐或公开目录发布。
