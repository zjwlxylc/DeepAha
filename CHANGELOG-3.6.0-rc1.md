# DeepAha 3.6.0-rc1 · SG6 持续监测、行动支持与反馈闭环

基线：用户已人工验收通过 `3.5.1-rc1 / SG5.1`。

## 新增

- `product_target_action_events`：具体机会行动时间线。
- `product_feedback_candidates`：脱敏离线反馈候选。
- 收藏/准备时自动建立 SG5.1 安全截止提醒；申请/等待/完成后自动取消报名提醒。
- 截止、变化、周摘要三类独立通知开关与提醒日设置。
- 周摘要：行动状态、7天内截止、机会变化和新的高价值候选。
- outcome feedback 与行动阶段同步；反馈不改变资格结论。
- `/api/me/actions/{id}/history`、`/api/me/weekly-digest`、`/api/manage/feedback-candidates`。
- 用户行动页时间线/结果反馈；通知页周摘要；管理端只读“反馈样本”。
- 个人导出包含完整行动事件（包括已经移出当前行动的历史）；清除个人数据覆盖 SG6 派生数据。
- `upgrade-sg6` backup-first 增量升级。

## 复用

- SG3 来源周期 `RECHECK`、Currentness/变化通知。
- SG4 Eligibility 硬资格门。
- SG5 Value/Priority 与 SG5.1 Evidence-backed Milestone。

## 明确不做

- 用户反馈直接改规则或事实。
- 全量 LLM 用户×机会评判。
- 微信/短信/邮件实际发送。
- SG7 Gold、数字分身或真人 Founding User 实验。
