# SG6.1 人工验收清单

## 用户端桌面

1. 顶部存在：发现 / 机会总览 / 我的机会星图 / 收藏与行动。
2. 右侧存在：消息 / 我的；有角色时再出现对应工作台。
3. 我的机会星图能看到行动摘要，并可直达收藏与行动。
4. `/app/actions` 在桌面浏览器可完整使用，不是手机专属功能。

## 角色入口

- user-only：不显示工作台；
- reviewer-only：显示 `审核工作台`，后台只有内容审核分组；
- operator-only：显示 `系统管理`，后台只有系统管理分组；
- reviewer+operator：显示 `工作台`，后台同时显示两组。

## 响应式与交互

- 360/390/430px：底部移动导航存在，桌面主导航隐藏；
- 768/1024px：桌面/平板导航可用，无整页横向滚动；
- 1440/1920px：布局不过度拉伸，工作台信息密度合理；
- 表单错误能在字段旁看到文字提示；
- 异步操作有 loading/disabled 反馈；
- 键盘 focus 清楚，skip link 可聚焦；
- 系统设置 reduced motion 后无不必要的位移动画。

## 业务回归

SG1–SG6 的 Opportunity、Currentness、Eligibility、Value、Milestone、行动、反馈、WMA/Scout 和 reviewer/operator 服务端权限必须保持原行为。
