# SG6 Implementation Plan

**Goal:** 在 SG5.1 已验收产品上建立持久行动时间线、安全提醒、周摘要、结果反馈和离线评估候选，并复用 SG3 周期来源监测。

**Architecture:** 当前状态与事件历史分离；提醒由 SG5.1 安全 Milestone 驱动；反馈结构化后进入独立 Candidate 表；硬事实与资格核心只读消费这些信号，不接受反馈写入。

**Tech Stack:** FastAPI, SQLAlchemy, SQLite/PostgreSQL-compatible ORM, vanilla JS product UI.

## 任务

1. RED：行动历史、结果同步、不改资格、通知独立开关、旧截止取消、周摘要幂等、数据清除。
2. GREEN：新增 ActionEvent/FeedbackCandidate 与 backup-first `upgrade-sg6`。
3. 编排：现有 `TargetAction/TargetFeedback/TargetNotice` 接 ActionLoopMixin。
4. API：行动历史、周摘要、反馈候选。
5. UI：行动时间线/反馈、通知设置/周摘要、只读反馈样本。
6. 复用：SG3 RECHECK 调度与 SG5.1 时间；不复制 Worker。
7. 验证：逐文件产品测试、Web 契约、compileall、用户真实多 WMA 数据副本回放、浏览器桥接。
8. 停止：SG6 人工验收前不进入 SG7。
