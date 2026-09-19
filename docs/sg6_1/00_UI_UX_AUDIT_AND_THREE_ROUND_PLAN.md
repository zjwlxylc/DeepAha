# SG6.1 UI/UX 三轮收口计划

版本：3.6.1-rc1。范围仅为表现层、导航、交互反馈、响应式和基础可访问性；SG1–SG6 业务语义冻结。

## 当前审查结论

1. 桌面用户导航漏掉 `/app/actions` 与 `/app/me`，导致 SG6 行动闭环在桌面不可发现；移动端底部导航已经具备这些入口，因此这是信息架构缺陷，不是手机专属设计。
2. 工作台权限后端已经按 `reviewer` / `operator` 分离，但 UI 对角色职责的表达仍弱；owner 只是拥有三角色的初始化账号，不需要新造 owner 角色。
3. 用户端、工作台、Scout、审核页经历多阶段追加，颜色、圆角、间距、按钮、表格密度、帮助文字和状态反馈存在局部不一致。
4. 表单有基础 label/focus，但缺少统一帮助文本、required/invalid 状态视觉、保存反馈层级；桌面/平板导航断点也偏粗。
5. 已有 prefers-reduced-motion 的局部处理，需要扩展到全局；键盘焦点、44px 点击目标、skip link、dialog、表格横向滚动提示需统一。

## Round 1 — 信息架构与布局

- 用户桌面导航：发现 / 机会总览 / 我的机会星图 / 收藏与行动；右侧：消息 / 我的 / 角色工作台。
- 角色工作台入口：reviewer-only=`审核工作台`；operator-only=`系统管理`；两者兼有=`工作台`。
- 星图新增行动摘要，明确“发现 → 收藏 → 准备 → 申请”的下一步。
- 工作台侧栏按权限动态显示“内容审核”“系统管理”分组，不再让 operator-only 看到含糊的“内容工作台”语义。
- 页面标题、主要操作、次要操作的位置统一。

## Round 2 — 视觉系统与组件一致性

- 建立 spacing / radius / shadow / focus / transition token。
- 统一按钮、输入、select、textarea、chip、pill、surface、table、empty、toast、dialog。
- 用户卡片、星图卡片、行动卡片、通知卡片、工作台面板统一层级：主信息 > 状态 > 辅助信息 > 操作。
- 表单统一 help / error / saved state；禁止只靠颜色表达状态。
- 管理表格降低重复边框噪声，增强 hover/focus 与可读性。

## Round 3 — 端到端精修

- 620 / 860 / 1024 / 1280 / 1440 / 1920 响应式审查。
- 44px 最小交互目标，键盘 focus-visible，skip link，dialog 焦点，aria-current。
- prefers-reduced-motion 全局降级。
- 路由切换加入轻量 loading 反馈，不清空已有页面。
- 移动端保留底部导航；桌面/平板不再出现信息入口缺失。
- 对长标题、长机构名、长 Evidence、空状态、错误状态做溢出和可读性收口。

## 不做

- 不改 Eligibility、Value/Priority、Currentness、Milestone、Action/Feedback 业务语义。
- 不增加新角色，不做复杂 RBAC。
- 不增加支付、SG7、真人实验或新 WMA 调用。
