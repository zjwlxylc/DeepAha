# SG6.2 真实 WMA 数据 Benchmark

基线：用户提供的多次 WMA 调用数据副本，328 个 CURRENT/UPDATE_PENDING Actionable Target。测试不写用户原始数据库，不调用 WMA。

## 1. SG6.1 → SG6.2

| 指标 | SG6.1 | SG6.2 |
|---|---:|---:|
| 当前 Target | 328 | 328 |
| requirements=0 | 189 | **0** |
| 完整测试画像 UNCERTAIN | 300 | **185** |
| 完整测试画像 INELIGIBLE | 28 | **139** |
| 完整测试画像 LIKELY_ELIGIBLE | 0 | **4** |
| Evidence LOCATED | 966 | **1543** |
| Evidence UNLOCATED | 88 | **278** |

`UNLOCATED` 数量增加不是退步：SG6.1 有大量 WMA 字段根本没有进入资格轨，因此从未接受 Evidence 检查。SG6.2 把这些字段纳入 compiler 后，才如实暴露其证据缺口。

## 2. 类真实用户画像

画像：专科、计算机、宁波；其他资格字段未强行填写。

| 状态 | SG6.1 | SG6.2 |
|---|---:|---:|
| INELIGIBLE | 97 | **199** |
| UNCERTAIN | 231 | **129** |
| requirements=0 | 189 | **0** |
| HIGH qualification risk | 0 | **100** |

300 个事业单位/招聘 Target 中：

- 199 个已由 SG4 以 Evidence-backed hard conflict 正式判定 `INELIGIBLE`；
- 100 个保持 `UNCERTAIN + HIGH RISK`，主要来自图像型扫描 PDF，原件存在但没有可验证、与原件哈希绑定的 OCR 派生文本；
- 1 个普通 `UNCERTAIN`。

SG5 headline 不再把这些高风险 UNCERTAIN 作为“今天真正值得你看的”Top 3；正式 Eligibility 仍然没有被推荐层改写。

## 3. 剩余 UNCERTAIN 为什么保留

高频原因包括：

- “相关专业/相近专业”等需要权威专业目录或可靠映射；
- 复合“其他条件”、符合其一、特殊例外；
- 学校/个人报名上限等并非单一用户静态画像即可裁决；
- 年龄条件缺少官方计算基准日期；
- Evidence 指向扫描 PDF，但没有保存且绑定原件哈希的 OCR 派生文本；
- 部分 team/application 条件 Evidence 仍无法定位。

这些不是待人工逐字段审核任务，而是明确的自动计算边界。只有未来获得更可靠的官方结构/Evidence 或新增确定性规则后，才可自动升级。
