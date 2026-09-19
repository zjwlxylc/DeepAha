# SG1_ACTIONABLE_GRANULARITY_DELIVERY

状态：`SG1_PASS`（2026-09-18，本地 SQLite + 用户上传真实 WMA 数据副本）。

## 目标

把机会总览从“父公告一张卡”改成“可独立行动的具体岗位/赛道/项目分项一张卡”，同时继续只对整份 WMA 返回做一次整体收录决定。

## 实现

- 新增 `OpportunityUnit`：保存跨修订稳定的 unit identity；GROUP 只做范围上下文。
- 新增 `CatalogTarget`：总览读模型；多岗位公告物化为多个 POSITION target。
- 新增 target-scoped Action / Feedback / Notice，避免 A01 收藏污染 A02。
- Catalog API target-first；父公告有独立读取入口。
- Unit own / ancestor / root common 字段分区展示。
- 审核页显示根机会数、全部结构分项与实际行动目标数，但仍只有一次 APPROVE / REJECT。
- RC2 SQLite 使用 `upgrade-sg1` backup-first additive 升级；启动器自动执行幂等检查。
- root-only 机会继续 singleton fallback；旧 root 级行动记录只读保留，不猜测子岗位。

## 真实数据结果

用户上传数据：1 根公告、58 GROUP、106 POSITION。升级后：1 Root Publication / 1 Decision 保持，164 Unit identities，106 Catalog Targets。

## 验证

- 后端产品测试：93 passed（最终 fresh run；详见 evidence）。
- 前端产品静态/契约检查：PASS。
- 真实数据库升级：backup verified，106 targets。
- 浏览器交互桥接：106 岗位、360/390/430 无溢出、单位/公告继承分区、target 收藏隔离；page errors=0。

## 环境边界

当前容器无外网，首次 `--install` 不能从 PyPI 获取 `codebuddy-cloud-agent-sdk==0.3.4`，因此没有把“全新环境联网依赖安装/Windows 双击启动”冒充为已验证。现有依赖环境中的后端、SQLite 升级、真实 API 和浏览器桥接均已验证；Windows 本机启动由用户本轮验收。

## 停止线

本交付不继续 SG2，不实现 AI 资格或推荐，不修改线上 WMA Agent，不 push / merge / deploy。
