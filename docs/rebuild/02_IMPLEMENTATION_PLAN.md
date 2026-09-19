# 重建实施计划与实际完成记录

**目标：** 从单次 WMA 返回到实际总览、个人行动闭环，替换旧默认运行路径。
**架构：** FastAPI 模块化单体；当前产品服务共用真实 SQL 数据与不可覆盖原件，WMA 独立执行。
**技术：** Python3.13、SQLAlchemy2、Pydantic2、ES Modules；SQLite 本地实测，PostgreSQL 配置路径待实测。
**设计依据：** `01_DESIGN.md`；原始输入 `references/2026-09-13-wma-overall-review-and-overview-replan.md`。

## 通用约束
原始库/远程仓库不改写；不代签真人；APPROVE 只收录；局部失败不自动整包拒绝；新读取/批准不能调用 WMA；资料库归档不等于系统导入；密钥不写入日志、Prompt、下载包。

## S1 原始输入与可信持久化
- [x] 提取原代码和 V2 视觉，记录 ZIP/规划哈希与远程观测差异。
- [x] 实现 `models.py/db.py/storage.py/auth.py`，复用实际 LocalFileObjectStore。
- [x] `test_contract.py`：先观察缺少服务/持久化路径的失败，再验证返回去重、原件完整性和角色隔离。
- [x] 明确初始化命令；读页面不隐式迁移，不生成默认账号或自动样本。

## S2 一次决定与总览
- [x] `adapter.py/intake.py/catalog.py/api.py`：同事务决定与展示、版本哈希、幂等回执、相反并发拒绝覆盖。
- [x] 测试正常、局部引用未定位、核心错配、陌生标签、日期冲突、旧版本过期和原件被改动。
- [x] 修复初次回执嵌套 JSON 原位变更未落库的问题；重复请求回读同一可用链接。
- [x] 千字段分页、长文本继续阅读、多对象一次决定、局部错误对象排除。

## S3 用户闭环与使用限制
- [x] `personal.py`：个人画像、相关性排序、行动、反馈、站内消息、日历、个人导出/清除。
- [x] 新版本/撤回取消旧日期动作，未知资格不升级，已知偏好不冒充录取概率。
- [x] 通知关闭对截止和变化消息均生效。
- [ ] 已训练 AI 排序、旧可信资格规则消费、对外通知和支付：本轮未接通，不标成已实现。

## S4 真实前端与维护
- [x] `web/public/product/*`：V2 视觉改为真实 API；无原型 fixtures、无业务 localStorage。
- [x] `sources.py/tasks.py/worker.py/config.py`：来源导入、任务、连接、安全本地凭据与恢复。
- [x] 周期检查绑定实际授权维护者，后续撤销权限会停止派发。
- [x] 源码 DirectWmaClient 复用；有明确假件测试，未实际调用腾讯。
- [x] 四个管理入口与普通审核互不前置；旧 Worker 直接执行拒绝。

## S5 交付与恢复
- [x] CLI、本地启动/停止、只读旧记录与受控旧 ID 关联。
- [x] SQLite 备份→校验→新目录恢复测试；不覆盖旧目录，恢复撤销旧会话。
- [x] Docker/NGINX/systemd 模板、API 描述、源码差异清单与使用手册。
- [x] 容器内接口/持久化与显式浏览器 HTTP 桥接验证，留存原始输出和截图。
- [ ] 原生浏览器 Cookie/CSP/导航验收、Windows、PostgreSQL、Docker 构建和真实 WMA：未在此环境完成。
- [ ] 原数据库备份迁移与真人验收：未执行，不能由工程测试代签。

## 可复现验证
```bash
cd backend
PYTHONPATH=src python -m pytest tests/product -o addopts= -q
cd ../web
node scripts/check-product.mjs
```
失败→修复→通过过程记录在 `evidence/`，最终总数看 `09_VALIDATION.md` 与本轮最终日志。旧全量测试包含其他运行时和数据库要求，不在此命令的完成声明内。
