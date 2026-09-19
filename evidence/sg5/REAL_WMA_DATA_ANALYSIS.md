# SG5｜用户新上传 WMA 数据分析

本报告基于用户上传的 `deepaha-data(1).zip` 的**离线副本**，原上传包未改写。

## 数据规模

- Tasks：9
- ResultSnapshot：7
- OverviewRevision：6
- OverviewDecision：6
- Publication：6
- Opportunity root identity：6
- Opportunity Units：425
- 当前 Catalog Targets：328

当前 Target 类型：

- `PUBLIC_INSTITUTION_JOB`：300
- `COMPETITION`：21
- `YOUTH_POLICY_BENEFIT`：7

这批数据非常适合 SG5 真实校准，因为同时包含大量岗位、竞赛赛道和政策分项；但它**没有覆盖科研、奖学金、升学等所有 SG2 类型**，这些类型仍由项目内虚构 fixture 做结构覆盖，不能把本批数据说成全类型真人数据。

## WMA 运行状态

任务表中除已完成任务外，还存在：

- `NEEDS_RECOVERY / COLLECTING`；
- `RUNNING / PROJECTING`；
- `CANCELLED / CREATING`。

SG5 不把这些技术运行状态解释成机会质量或事实真假；排序只读取已经形成当前 Catalog Target 的内容。

## 真实排序回放

### 场景 A：用户只写“宁波 + 政策”

系统把 `YOUTH_POLICY_BENEFIT` 作为**召回提示**，候选 67 个；前 7 个均为真实宁波一次性求职补贴的条件分项。之后仍保留少量招聘探索候选。

这修正了旧式文字排序容易把“政策传播岗”等招聘内容排在真正政策前面的假相关问题。

### 场景 B：显式选择人才政策

候选池收敛到 7 个真实政策 Target，均为政策类；显式类型偏好是强召回条件。

### 场景 C：显式选择竞赛 + AI

候选池为 21 个真实竞赛赛道，Top 项包括工业图像异常检测、开源鸿蒙 AI+边缘智能、AIGC 城市短视频等赛题。

## 当前真实数据缺口

很多原始材料中存在时间描述，但当前 Target 并没有可安全用于计算的 canonical deadline，SG4 也未对这些条目生成 Evidence=`LOCATED` 的精确行动日期。因此 SG5 正确保持：

> 时间节点尚未明确。

它不会从正文自由文本里自行解析一个精确日期再制造倒计时。这是有意的安全边界，而不是排序缺陷。

## 字段质量补充统计

对 328 个 CURRENT Target 的直接投影检查：

- canonical `deadline` 非空：**0**；
- canonical `deadline` 为空：**328**；
- 但字段层中“报名截止/registration_deadline”等原始或结构化文字大量存在。

因此当前瓶颈不是“WMA 没有看到时间”，而是这些时间尚未全部经过 SG4 所要求的 **当前版本 + 明确作用域 + 可定位 Evidence + 安全规范化** 进入可计算日期轨。SG5 不越权补做自由文本日期解析。

地区字段也呈现真实世界复杂性，例如“河北省多个市分公司”“浙江省（决赛地点+秘书处）”“浙江省多个城市”等，并非单一城市枚举。因此 SG5 V1 采用可解释的子串/偏好匹配，并把地区未知保留，而没有把复合地点强制归一成单城市事实。
