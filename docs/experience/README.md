# 机会星图 · 体验改善整合版

交付标识：**experience-84353c7-20260920**。业务版本仍是 SG8-A / 3.8.0-rc1；本标识区分本次新增工程，不冒充原正式站版本。

源码基线是 `84353c7e5286e276d24af8e0342d4d3441c30ec5`。本包是完整源码，不是独立 HTML 原型或差异补丁。没有推送 GitHub，也没有修改正式站、隔离 staging、Nginx、Ops Gateway 或宿主秘密。

## 本次可以直接使用的改进

| 计划 | 实际实现 | 主要文件 / 验证 |
|---|---|---|
| A0 | 统一局部组件、导航、弹窗焦点；320/390/1440 适配；原图形 LOGO 不变 | experience.css / core.js / 浏览器记录 |
| A1 + B2 | 画像只提交实际修改字段；显式清空；事务版本校验；409 保留草稿，展示差异后再确认 | profile-editor.js / personal.py / test_experience_api.py |
| A2 | 原 v22 三海报首屏 + 原末尾品牌区；移除中间解释屏；总览筛选返回；资格、推荐与时间分开；六状态行动看板/列表 | home.js / user.js / actions-ui.js |
| A3 | 整份返回一个决定；硬阻断与一般备注区分；手机只读工作台；旧 preview_hash、幂等键和撤回版本保护保留 | workbench.js / 原审核回归 |
| B1 | 来源与任务服务端全量查询、独立总计、分页、来源远程选择、任务详情和下一步指引 | experience.py / operations-ui.js |
| B3 | 个人准备清单真实持久化、按用户与目标隔离、版本关联、导出与清除；未读筛选和当前页批量已读 | preparation_items / notification-list 接口与测试 |
| C1 工程 | 宿主命名连接、发布绑定指纹、串并行策略、队列/预算/域名限额、事务领取、租约隔离、恢复不重发 prompt、显式实测工具 | dispatch_policy.py / worker.py / live_validation.py |
| D1 工具 | 真人验收任务、空白记录表、放行及回退清单 | HUMAN_ACCEPTANCE.md / human_acceptance.csv |

**未完成的真实验收必须单独保留：**真实 WMA 单任务及 2/4 并发、PostgreSQL 实机迁移与并发/恢复、Windows 原生启动、真实手机、真人任务验收、正式发布均未执行。D1 不能以自动化截图代替。C1 未实测的连接默认有效并发 1，其他模型也不会直接放开。

## 首页来源

使用本次上传 `DeepAha_机会星图_原型源码_v22_2026-09-20(1).zip` 中 `app/prototype-v1.tsx` 的 OpportunityCarousel/Landing 结构及原始三组海报。适配为原生模块，不复制 React 本地模拟账户、假机会、原型数据状态机或内联脚本。`web/public/product/brand-logo.png` 与 `84353c7` 字节一致。

海报支持轮播、手动切换、暂停、左右键、触摸滑动、减少动态效果；第一张优先加载。原型海报自带文字的部分保留，不重新生成或修改图形 LOGO。

## 阅读顺序

`RUN_AND_UPGRADE.md` 是本地运行/升级入口；`API_AND_ARCHITECTURE.md` 记录新增接口；`WMA_EXECUTION.md` 说明宿主绑定与实测；`TEST_REPORT.md` 区分已验证和未验证；`RELEASE_AND_ROLLBACK.md` 用于后续宿主人工发布。

原始 `00–03` 计划文档保留为历史输入，里面的“仅交互原型”“先只做 A”是当时阶段安排，不是本包交付状态。当前实现与门禁以本 README、测试报告和 `DELIVERY_STATUS.json` 为准。
