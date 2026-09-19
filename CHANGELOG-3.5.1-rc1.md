# DeepAha 3.5.1-rc1 · SG5.1 时间语义与收录管理收口

基线：用户已人工验收通过的 `3.5.0-rc1 / SG5`。

本轮不进入 SG6。只解决两个已经由真实 WMA 数据暴露的问题：**安全时间节点不能充分进入计算轨**，以及**收录管理把数百个具体机会平铺成重复列表**。

## 时间语义

- 新增 Evidence-backed Milestone 投影：`APPLICATION_OPEN / APPLICATION_DEADLINE / SUBMISSION_DEADLINE / REVIEW_WINDOW / PAYMENT_WINDOW / ADMISSION_TICKET_WINDOW / EXAM_DATE / INTERVIEW_DATE / RESULT_DATE / ROLLING_APPLICATION`；
- 支持“报名时间 2026年8月13日9:00—8月19日16:00”这种范围拆成开始与截止；
- 支持“更正后 / 原定”版本优先级；
- 支持滚动受理，不制造虚假精确截止；
- 同级多个冲突截止并列保留，禁止倒计时；
- SG3 `UPDATE_PENDING` 的时间字段停止用于提醒；
- 证据不仅必须定位，还必须真正包含被规范化的日期/时刻；Evidence 引用日期与字段值不一致时不计算；
- “报名方式 / 申请方式 / 报名上限”等非时间字段不会污染时间质量；
- 新增 backup-first、幂等 `upgrade-sg5-1`，启动器自动执行；不重新调用 WMA。

## 收录管理

- `/review/catalog` 默认改为**按父公告 / 根机会**组织，而不是数百条具体机会平铺；
- 顶部运营摘要：当前具体机会、父公告数、更新待处理、时间待确认、已过截止；
- 每个父公告展示：具体机会数、状态分布、时间质量分布、最早安全截止、最近更新、代表性分项；
- 可展开具体岗位/赛道/政策分项；
- 保留“按具体机会”第二视图，用于精确搜索和单 Target 撤回；
- 不增加父公告一键撤回默认动作；
- 新增时间质量筛选：`READY / ROLLING / NEEDS_ATTENTION / CLOSED`。

## 真实 WMA 数据结果

对用户上一轮上传的 328 个当前 Target 副本执行 SG5.1 回填：

- 282 个 Target 得到可计算 `APPLICATION_DEADLINE`；
- 其中 68 个当前仍为 OPEN，214 个已经 CLOSED；
- 46 个保持 PARTIAL，因为相关日期 Evidence 未定位或不能安全支撑当前字段；
- 0 个日期由未定位字符串直接制造；
- 六个 Root 仍为六个 Root，328 个 Target 数量不变；
- 第二次升级 `already_current=true / data_modified=false`。

## 停止线

本候选版停止在 SG5.1，等待用户 Windows 本机人工验收；未进入 SG6。
