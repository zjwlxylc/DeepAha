# DeepAha 3.7.2-rc1 / SG7.2

## 目标

把已经在 `deepaha.com` 产品化原型中确认的首页 / 品牌表达迁入 SG7.1 真实产品，并新增正式“关于我们”，解决 SG7.1 首页偏工程化、视觉完成度不足的问题。

## 主要变化

- `/` 重构为真实产品首页：首屏 → 找到 → 判断 → 行动 → 品牌收束；
- `/about` 新增正式关于我们页面；
- 用户提供的新 Logo 进入统一 `brand()` 组件，并成为 favicon；
- 公开首页与登录后的机会星图保持同一 SPA / 同一 API / 同一数据；
- 首页 CTA 直接进入真实机会总览和个人星图；
- 保留官方证据、可能符合、待确认等可信表达；
- 明确不复制公网演示中的 `94%` 等伪精确匹配分；
- 新增 SG7.2 前端合同测试与响应式样式。

## 不变

- WMA；
- Candidate / overall review / Catalog；
- SG6.2 Qualification Compiler；
- SG4 Eligibility；
- SG5 Value / Priority；
- SG7.1 Lab / Twin V2 / Gold Oracle；
- 数据库结构与现有用户数据。

## 验证

- 29 个产品测试文件 / 221 tests；
- 29/29 独立 RC=0；
- Python compileall PASS；
- product / SG5 / SG5.1 / SG6 / SG6.1 / SG7 / SG7.1 / SG7.2 前端契约 PASS。

状态：**SG7_2_ENGINEERING_SELF_TEST=PASS / Windows 本地人工验收候选**。
