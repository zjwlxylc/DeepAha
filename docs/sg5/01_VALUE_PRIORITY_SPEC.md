# SG5 Value / Priority 规格

## 1. Progressive User State

SG5 在既有资格画像之外新增可选字段：

- `opportunity_types`：显式希望优先关注的机会类型；
- `career_directions`：发展方向；
- `cities`：地区偏好；
- `region_preference_mode`：`FLEXIBLE / PREFERRED / STRICT`；
- `interests`：兴趣；
- `goals`：当前目标；
- `skills`：技能与优势；
- `constraints`：个人限制，仅作为解释/排序上下文，不自动变硬资格；
- `personalization_enabled`：用户可以关闭个性化排序。

身份信息、手机号等不进入 SG5 排序。SG5 不向 WMA 或外部模型发送画像。

## 2. Candidate Retrieval

候选召回必须有界，首版 `candidate_limit <= 120`：

- 显式选择机会类型：优先按类型召回；
- 未显式选择时：允许从兴趣/目标/发展方向推断**召回提示**，但不得把推断类型写回事实库；
- 保留少量探索候选，防止画像过窄导致信息茧房；
- `DISMISSED / COMPLETED` 不进入发现流；`SAVED` 可以保留；
- `STRICT` 地区模式只过滤**已知明确不匹配**的地区，地区未知不作负面推断。

## 3. Eligibility Gate

每个候选进入 Value 排序前必须调用 SG4：

- `INELIGIBLE`：从个性星图硬过滤；
- `ELIGIBLE / LIKELY_ELIGIBLE / UNCERTAIN`：可继续参与 Value；
- `UNCERTAIN` 必须在解释中保留风险，不能包装成“高概率符合”。

## 4. Value Features

V1 只使用可解释、本地、可回放特征：

- opportunity type preference；
- region preference；
- interests；
- goals；
- career directions；
- skills；
- safe timing；
- action state；
- negative feedback；
- currentness risk；
- eligibility state。

内部可以有确定性排序分值，但**公共 API/UI 不返回数值匹配分**。

## 5. Timing / Why now

只允许使用：

1. Target 已有 canonical deadline；或
2. SG4 输出中 `APPLICATION_DEADLINE` 且 Evidence=`LOCATED` 的 normalized date。

正文中出现“9月”“年底前”“常年受理”等字符串，不得为了排序自行编造成精确日期。

## 6. Priority Bands

公开只展示离散级别：

- `ACT_NOW`：可靠行动窗口较近，且具有明显个人价值；
- `HIGH`：值得优先关注；
- `RELEVANT`：与当前画像有明确关联；
- `EXPLORE`：探索性机会；
- `NOT_RECOMMENDED`：不进入当前个性星图。

Priority 不是成功概率。

## 7. Explanation Contract

每个 SG5 Target 返回：

- `why_for_you[]`；
- `why_now`；
- `risks[]`；
- `eligibility_status`；
- `priority_band`；
- `basis=LOCAL_VALUE_PRIORITY_V1`；
- `llm_used=false`。

不得输出成功概率、录取概率或伪精确匹配百分比。

## 8. Top-N

首屏 `featured` 默认最多 3 个，并优先来自不同 Opportunity Root，避免同一公告的相邻岗位占满整屏。剩余候选进入“继续探索”。

## 9. 升级路径

未来学习模型只能替换/增强排序函数，不得绕过：

- Actionable Target identity；
- SG3 Currentness；
- SG4 Eligibility hard gate；
- Explanation / audit contract；
- 用户关闭个性化的权利。
