# SG6 行动与反馈闭环规格

## 1. 行动是用户自己的历史，不是机会事实

行动状态：`SAVED / PREPARING / APPLIED / WAITING / COMPLETED / DISMISSED`。当前状态保存在 `TargetAction`，每次变化另写 `TargetActionEvent`。删除当前行动行不能抹掉个人历史；个人导出仍包含事件。

## 2. 提醒只相信安全时间

自动截止提醒只能使用 CURRENT Target 中 SG5.1 生成且 `time_readiness.state=READY` 的 `deadline`。Target 进入 `UPDATE_PENDING`、旧时间被发现不可靠、机会撤回或用户进入申请后阶段时，旧报名提醒必须取消。

通知通道互相独立：总开关、截止、变化、周摘要。关闭“变化”只抑制消息，不得阻止旧截止失效。

## 3. 周摘要

每 ISO 周最多一条。内容只聚合：进行中的行动、7天内安全截止、Currentness 变化、少量新的 SG5 高价值候选。它不重新定义资格或价值。

## 4. 反馈

反馈允许：以前是否知道、是否有用、不行动原因、结果和可选自由文字。结构化结果可推动用户自己的行动阶段；SG4 Eligibility 在反馈前后必须一致。

后台只保存/展示脱敏 `FeedbackCandidate`：机会类型、结构化反馈、行动状态、outcome、是否含自由文字。不得包含账号名、完整画像或自由文字内容，也不得直接写 Rule/VerifiedFact。

## 5. 持续监测

继续使用 SG3 `SourceProfile.interval_hours/next_due → RECHECK Task`。SG6 不创建新的来源监测器。RECHECK 发现变化后继续走 SG3 新版本审核；SG6只负责把变化转换成用户行动层通知和提醒更新。

## 6. 数据权

`/api/me/export` 包括画像、当前行动、完整 TargetActionEvent、反馈；`DELETE /api/me/data` 删除画像、行动、行动事件、反馈、派生 FeedbackCandidate 和个人通知，但不删除公开机会库。
