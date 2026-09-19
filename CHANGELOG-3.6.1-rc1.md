# DeepAha 3.6.1-rc1 · SG6.1 UI/UX 三轮产品收口

基线：3.6.0-rc1 / SG6。SG1–SG6 业务语义冻结；本版本只修改表现层、导航、交互反馈、响应式和基础可访问性。

## Round 1 — 信息架构

- 桌面用户端补齐 `收藏与行动`、`我的`，打通星图 → 收藏 → 行动链。
- 我的机会星图新增行动摘要与直达入口。
- reviewer-only / operator-only / combined 三种角色入口分别显示 `审核工作台` / `系统管理` / `工作台`。
- 工作台按 `内容审核` 与 `系统管理` 分区，并提供 `收藏与行动 / 返回用户端`。

## Round 2 — 视觉与组件

- 统一 spacing / radius / shadow / focus / motion / content width token。
- 统一按钮、输入、卡片、表格、状态标签、toast、dialog、空状态。
- 异步按钮增加 loading 和 aria-busy；表单增加原生校验的行内错误反馈。
- 用户端与工作台使用同一视觉语法和状态层级。

## Round 3 — 响应式与可访问性

- 收口 360–1920 响应式布局与窄桌面工作台。
- 主要交互目标至少 44px；补强 focus-visible、skip link、aria-current。
- 路由切换加入轻量 loading 状态。
- 全局支持 `prefers-reduced-motion`。
- 长标题、长机构名、Evidence、表格等不再造成页面级横向溢出。

## 明确未改变

- 数据库 Schema 与业务表；
- WMA 调查、审核、发布、Currentness、Eligibility、Value、Milestone、行动与反馈语义；
- reviewer/operator 服务端权限模型；
- SG7 及之后功能。
