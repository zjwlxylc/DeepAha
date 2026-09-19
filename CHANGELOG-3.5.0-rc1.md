# DeepAha 3.5.0-rc1 · SG5

基线：用户已人工验收通过的 `3.4.0-rc1 / SG4`。

## 新增

- Progressive User State：机会类型、发展方向、地区偏好强度、个人限制、个性化开关；
- 有界 Candidate Retrieval，默认最多进入 120 个深评候选；
- SG4 Eligibility hard gate：`INELIGIBLE` 不进入个性星图；
- 本地 `LOCAL_VALUE_PRIORITY_V1` Value/Priority 引擎；
- `ACT_NOW / HIGH / RELEVANT / EXPLORE` 离散 Priority Band；
- “为什么值得我关注 / 为什么现在 / 需要注意”解释；
- Top-N root diversity；
- `GET /api/me/value/{target_id}`；
- 手机端“今天真正值得你看的”机会星图；
- 用户可关闭个性化排序，机会总览继续可用；
- 真实 WMA 328 Target 离线排序回放与数据分析。

## 安全边界

- 不调用 WMA/外部 LLM 做全量个人排序；
- 不产生成功率、录取概率或伪精确匹配百分比；
- 画像语义推断只作为召回提示，不写回事实、不改变 Eligibility；
- 时间不确定时不制造倒计时；
- SG3 `UPDATE_PENDING` 进入风险提示；
- `constraints` 不自动升级成硬资格。

## 数据库

SG5 **没有新增数据库 Schema 迁移**。新画像字段继续存储于 Profile JSON，Value/Priority 按当前 Target、当前画像和当前 SG4 资格结果实时计算。

## 停止线

本候选版停止在 SG5，等待用户本机人工验收。未进入 SG6 持续监测、反馈学习和通知闭环。
