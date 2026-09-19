# SG5 Personal Opportunity Value / Priority Delivery

## 变更文件

- `backend/src/deepaha/product/value.py`：新增本地 Value/Priority 引擎；
- `backend/src/deepaha/product/personal.py`：Progressive User State、有界召回、SG4 Gate、Top-N 编排；
- `backend/src/deepaha/product/api.py`：新增 `GET /api/me/value/{target_id}`；
- `web/public/product/user.js`：星图 Top-N、价值解释、画像字段和关闭开关；
- `web/public/product/product.css`：SG5 星图与解释样式；
- `backend/tests/product/test_personal_value.py`：SG5 核心 TDD；
- `web/scripts/check-sg5.mjs`：前端契约检查。

## 关键设计取舍

### 没有新数据库迁移

SG5 画像字段继续存在 `Profile.data` JSON；排序结果按当前 Target、当前画像和 SG4 结果即时计算。首版不持久化一个会迅速过期的“匹配分”。

### 没有外部模型依赖

SG5 V1 的召回、资格门、价值特征、Priority 和解释全部在 DeepAha 本地完成。后续若引入 learning-to-rank 或 Top-K LLM 深解释，必须保持同一接口边界。

### 推断类型只是召回提示

例如画像只写“政策”，系统可以优先召回 `YOUTH_POLICY_BENEFIT`，避免“政策传播岗”这种文字假相关排在真正政策前面；但这个推断不写回用户事实、不参与资格裁决，也不会把用户锁死在一种类型里。

## 与旧能力的关系

- SG1：继续使用 Target identity；
- SG2：使用 Opportunity type / presentation；
- SG3：UPDATE_PENDING/当前性进入风险；
- SG4：INELIGIBLE 是硬过滤，其他三态保留风险；
- SG6：反馈学习尚未实现，本轮只读取已有行动/负反馈做最小排序影响。
