# SG6.2 Qualification Evidence Compiler 设计

## 目标
在不恢复逐字段人工审核、不新增逐岗位审批、不降低 SG4 证据门的前提下，把 WMA 已经提取且有可靠原件支持的资格条件自动编译成 SG4 可计算的 canonical qualification conditions，并形成可解释 coverage / unresolved 清单。

## 不做
- 不恢复事实/规则逐字段 HUMAN 审核。
- 不允许 reviewer 在审核页逐项确认学历、专业、年龄。
- 不允许 WMA 自己批准 VerifiedFact、Rule 或 Eligibility。
- 不用 LLM/Agent 做最终硬资格裁决。
- 不把 `UNCERTAIN` 强制变成正/负结论。

## 架构
WMA Candidate Facts -> Canonical Field Alias -> Qualification Compiler -> Evidence Resolver -> Canonical Conditions + Coverage -> SG4 Deterministic Evaluator.

Compiler 只接受当前 Catalog Target + 当前 Revision/Snapshot。显示与计算分离：原字段始终可展示；只有安全编译成功的条件进入计算轨。

## Canonical 字段
首版覆盖招聘/事业单位高频硬条件：
- EDUCATION_MIN
- DEGREE_MIN
- MAJOR_CODE_SET
- GRADUATION_YEAR_SET / FRESH_GRADUATE
- BIRTH_DATE_MIN
- HUKOU_REGION
- NATIONALITY
- POLITICAL_STATUS
- EXPERIENCE_MIN_YEARS
- CERTIFICATE_REQUIRED
- TITLE_REQUIRED
- LANGUAGE_CERTIFICATE

字段名统一支持中英文/常见别名，例如 education/学历/学历要求；major/专业/专业要求；experience/工作经历；degree/学位；political_status/政治面貌。

## Evidence
保留 SG4 HTML/TXT/XLSX 校验，并扩展 DOCX/PDF/OCR 派生文本的只读定位：
- DOCX：读取段落/表格文本，quote 必须能在对应原件文本中找到；
- PDF：优先使用已保存的派生文本/OCR artifact 与原 PDF 的 lineage/sha 绑定；没有可核验文本层则 UNLOCATED；
- 图片/OCR：只有已保存 OCR 派生 artifact、能关联原图 hash、quote 可匹配时才算 LOCATED；不能现场 OCR 猜测。

## Coverage
不再信任 WMA 单个 `qualification_coverage` 字符串作为完整性真值。服务端生成 `compiler_coverage`：
- COMPLETE：存在显式资格条件清单，所有硬条件均成功分类，且没有 unresolved hard condition；
- PARTIAL：至少一个 canonical condition，仍存在 unresolved；
- NONE：没有安全编译出的硬条件。

SG4 `ELIGIBLE` 只允许：coverage COMPLETE + 所有硬条件 SATISFIED + 当前版本无 pending。
`LIKELY_ELIGIBLE`：至少一个安全条件且无冲突、coverage PARTIAL、无 unresolved mandatory block。
`UNCERTAIN`：有 unresolved / evidence gap / profile gap / semantic gap。
`INELIGIBLE`：仍只允许证据充分、确定性硬冲突。

## 资格风险（供 SG5 门控）
SG6.2 同时输出 `qualification_risk`，不改变正式 Eligibility：
- HIGH：原文存在明显学历/学位/年龄/专业等潜在硬冲突，但因证据/语义门未能形成正式 INELIGIBLE；
- NORMAL：没有明显潜在硬冲突。
SG5 Top-N 后续可使用该字段把 HIGH-risk UNCERTAIN 从主推荐降到继续探索，但本轮不改变 SG5 排序语义，避免扩大范围。

## 数据与迁移
SG6.2 首版不新增新权威事实表。compiler 输出作为 CatalogTarget 的可重建派生 metadata 缓存，可通过 upgrade-sg6-2 批量重算；原 Revision/Snapshot/Publication/Decision/objects 不改写。

## 验收
1. 英文字段 education/major/experience 能被识别。
2. 学位、国籍、政治面貌、经历、证书等不再全部落 UNSUPPORTED。
3. DOCX/PDF/OCR 有可验证派生文本时能定位；无可验证文本时保持 UNLOCATED。
4. 真实 WMA 数据的 requirements=0 Target 数显著下降。
5. COMPLETE/PARTIAL/NONE coverage 由服务端自动生成。
6. 任何 unresolved 或证据不足都不能产生新的错误 INELIGIBLE。
7. 无逐字段审核 UI/API；整体审核流程不变。
