# 依据与外部技术资料

## 项目依据
以当前用户重新开发的委托和 `references/2026-09-13-wma-overall-review-and-overview-replan.md` 为最新业务基线。V2样式来自本次上下文已有交付；原代码基线及哈希见input-manifest。历史早期方案、前次原型测试数字和旧代码报告不自动作为本轮验证事实。

## 官方技术资料（本轮查阅，仅用于架构/部署接口说明）
- FastAPI Docker部署：https://fastapi.tiangolo.com/deployment/docker/
- SQLAlchemy2 Session事务：https://docs.sqlalchemy.org/en/20/orm/session_transaction.html
- PostgreSQL18 SQL备份：https://www.postgresql.org/docs/18/backup-dump.html
- 腾讯云WorkBuddy Enterprise/WMA快速开始：https://cloud.tencent.com/document/product/1831/134527

本轮没有从这些说明推导出未公开的模型覆盖、Webhook、磁盘配额或付费套餐参数。WMA实际传输采用原仓库已有实现；部署模板与文档不等于对应第三方服务已经验收。
