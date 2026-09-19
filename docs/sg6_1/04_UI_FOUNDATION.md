# DeepAha Product UI Foundation v1.0

适用起点：**3.6.1-rc1 / SG6.1**。后续产品开发默认继承本规范；除非有明确产品理由，不重新发明另一套导航、间距、状态或组件语言。

## 1. 信息架构

### 用户端桌面

一级主导航固定为：

1. 发现
2. 机会总览
3. 我的机会星图
4. 收藏与行动

右侧工具区固定承载：

- 角色工作台入口（仅有相应角色时出现）；
- 消息；
- 我的。

角色工作台名称：

- reviewer-only：`审核工作台`
- operator-only：`系统管理`
- reviewer + operator：`工作台`
- user-only：不显示工作台入口

`owner` 不是角色名；初始化 owner 账号只是同时具有 `user + reviewer + operator`。

### 用户端移动

底部导航固定为：发现 / 总览 / 星图 / 行动 / 我的。消息保留在顶部工具区。移动端不得因为空间不足删掉行动入口。

### 工作台

侧栏按真实权限分区：

- `内容审核`：reviewer 能力；
- `系统管理`：operator 能力。

工作台顶部必须提供 `收藏与行动` 和 `返回用户端`，避免角色用户进入后台后失去个人产品上下文。

## 2. 设计 token

统一从 `brand-v2.css` 读取：

- 品牌蓝 / Aha 橙 / 语义状态色；
- `--space-*` 间距阶梯；
- `--radius-*` 圆角；
- `--shadow-*` 阴影；
- `--focus-ring`；
- motion 时长与 easing；
- 用户端/窄内容宽度。

业务页面不得随意新增近似蓝色、圆角、阴影和间距常量。需要新 token 时先确认是否真的是新的视觉语义。

## 3. 页面层级

标准页面顺序：

`页面标题/一句解释 → 当前最重要的状态或摘要 → 主任务内容 → 次要信息 → 辅助操作`

主要 CTA 每个视区尽量只有一个。危险操作不使用主蓝按钮。

卡片内信息顺序：

`状态/类型 → 标题 → 来源/地点/时间 → 与我相关的解释 → 风险/待确认 → 操作`

## 4. 组件规则

按钮、input、select、textarea、chip、pill、surface、table、toast、dialog、empty state 必须复用 `product.css` 的统一基线。

- 主要交互目标最小高度 44px；
- 错误不能只靠红色表达，必须有文字；
- `aria-invalid` 与对应 `.field-error` 联动；
- 异步按钮使用 loading/disabled/`aria-busy`；
- toast 区分 info/success/error；
- dialog 打开后将焦点移入；
- 长 URL、Evidence、机构名必须允许换行或局部滚动，禁止造成整页横向溢出。

## 5. 响应式基线

- `>1120px`：完整桌面体验；
- `901–1120px`：紧凑桌面，右侧工具以图标优先；
- `621–900px`：平板/窄桌面；工作台缩窄，内容改单列或双列；
- `<=620px`：移动产品形态，用户端切到底部导航；复杂工作台提示使用电脑端完成。

验证宽度至少覆盖：360 / 390 / 430 / 768 / 1024 / 1440 / 1920。

## 6. 可访问性与动效

- 页面必须保留 skip link；
- 当前路由使用 `aria-current="page"`；
- 键盘焦点必须可见；
- 动态状态使用 `aria-live` 或明确状态文字；
- route transition 使用轻量 loading，不闪白、不清空整个旧页面；
- `prefers-reduced-motion: reduce` 时关闭非必要动画与位移；
- 不以 hover 作为唯一可用方式；
- 状态不只靠颜色区分。

## 7. 业务边界

UI 不得为了“体验更顺”改变以下业务事实：

- SG1 Actionable Target 粒度；
- SG2 多类型 Opportunity；
- SG3 Currentness/版本状态；
- SG4 Eligibility 四态与 Evidence 边界；
- SG5 Value/Priority；
- SG5.1 安全 Milestone；
- SG6 行动/反馈闭环；
- reviewer/operator 服务端权限。

前端隐藏按钮永远不替代服务端授权。

## 8. 新页面上线前最小 UI Gate

1. 信息入口在桌面和移动端均可发现；
2. 360–1920 代表宽度无页面级横向溢出；
3. 主要操作 44px 触摸目标；
4. focus-visible、aria-current、空状态、错误状态齐全；
5. reduced-motion 可用；
6. 不重复创造已有组件；
7. 角色入口与后端权限语义一致；
8. 通过 `check-product.mjs` 与最新 SG UI 契约检查。
