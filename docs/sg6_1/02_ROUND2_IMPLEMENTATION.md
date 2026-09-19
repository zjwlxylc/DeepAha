# Round 2 实施说明

目标：形成可以后续延续的 DeepAha Product UI Foundation。

代码改动：
- `brand-v2.css`：补充设计 token（spacing/radius/shadow/focus/motion/type）。
- `product.css`：按钮、表单、卡片、表格、toast、dialog、状态标签统一；工作台与用户端使用同一视觉语法。
- `user.js/workbench.js`：补充统一的辅助说明、状态容器和主要操作层级，不改 API 契约。

验收：同类控件视觉/交互一致；状态不只靠颜色；长内容不破版；主要操作视觉优先级稳定。
