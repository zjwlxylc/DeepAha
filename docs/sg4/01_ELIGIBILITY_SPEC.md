# SG4 Evidence-backed Eligibility Spec

## 两条数据轨

**Display Lane** 保留 WMA 原文、备注与一次整体审核；**Computation Lane** 只消费当前、作用域明确、Evidence 可定位、能够确定性归一化的硬条件。展示通过不等于可计算。

## 四态

- `ELIGIBLE`：明确声明资格覆盖完整，且所有当前可计算硬条件都有证据并满足。
- `LIKELY_ELIGIBLE`：当前可计算硬条件全部满足，但材料未证明资格条件覆盖完整。
- `UNCERTAIN`：画像缺失、Evidence 未定位、例外/OR/复杂语义、条件未支持、SG3 受影响内容更新待收录等。
- `INELIGIBLE`：至少一项**当前官方 Evidence 支持的明确硬条件**与画像发生确定性冲突，或证据支持的报名窗口已关闭。

## 首版可计算字段

学历最低层级、明确毕业年份、明确专业代码集合、明确出生日期截止/有双边证据支持的年龄解释、明确户籍地区、准确报名截止。

“相关专业”“应届毕业生”“满足其一”“可放宽”“另有规定”等无法安全确定性展开的表述不做硬否定。

## Evidence

文本 Evidence 继续复用 intake 阶段对保存原件的 quote 定位结果。XLSX Evidence 在资格计算时重新从 immutable object store 读取字节，校验 snapshot SHA，再按 Sheet/Row/Column 核对单元格值。损坏、哈希不符、单元格不匹配均 fail closed。

跨字段年龄条件要求岗位年龄 Evidence 与父公告解释 Evidence 同时可定位。父公告“38周岁以下专指……”本身不是所有岗位的全局限制。

## Currentness

SG3 `UPDATE_PENDING` 的受影响字段不得产生最终硬否定。未受影响且仍当前的独立硬条件可以继续计算。`MISSING_PENDING/WITHDRAWAL_PENDING` 等整目标不确定场景整体保持 UNCERTAIN。

## 权威边界

WMA `CONFIRMED` 只是候选内容状态。SG4 不创建 legacy VerifiedFact/RuleSet，不恢复逐字段审批，不调用 LLM 裁决，不改变 SG1/SG2/SG3 的发布与版本语义。
