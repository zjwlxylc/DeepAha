# 信源资产对齐实施计划

目标：在rc1上交付可运行的候选接收、来源批准与反馈闭环。
架构：复用模块化单体、现有事务/权限/对象存储/来源/WMA；纯离线适配独立模块。
技术栈：沿用Python 3.13、FastAPI、SQLAlchemy与现有原生JS；不新增远程服务。
设计依据：01_DESIGN.md；工具v0.3.1实际Schema与源码。

## S1 输入与服务端重建
- 先建立原工具真实Workspace.export生成的测试ZIP及篡改用例。
- 移植仅离线读取/规范化/审计代码到product/scout_research，保留来源文件哈希。
- 新建product/scout_package.py执行外层Manifest、bundle_id、原件核对；服务端重算。
- 测试：正常原包、WB嵌套研究包、State非候选、无schema、变更Audit、原件哈希、越界、成员配额。

## S2 持久接收与接口
- 新建product/scout.py与独立数据模型；复用Database.tx与ArchiveStore。
- 新增api/manage/scout/capabilities、previews、batches、observations、receipts、feedback。
- 接收参数只接受preview_hash、selected_ids、request_key，不接受actor或verified。
- 测试：未登录401、无权限403、CSRF、预览无正式写入、事务回滚、重复、重启回读、run冲突与跨研究族隔离。

## S3 批准与WMA
- 以一次明确表单批准选定观察；保留候选与Source不同身份。
- 保存来源政策版本、完整选用Brief、稳定候选/原包引用，默认停止调度。
- TaskSourceContext冻结批准过的来源与Brief；Worker只在原有授权下使用。
- 测试：伪造外部Source ID无效、同URL需显式绑定、错版本409、晚到旧记录不覆盖、WMA离线仍可接收、无自动任务。

## S4 成品界面与反馈
- 新增web/public/product/scout.js并接入管理导航，保留原来源手工登记。
- 从持久事件生成与工具v0.3.1兼容的scout-feedback.v1；重复下载稳定。
- 测试真实浏览器（受限时明确记录替代范围）、界面搜索/分页/提交/批准、工具inspect_feedback回读。

## S5 收口
- 运行新增定向测试、原产品回归及前端语法检查，记录实测环境。
- 更新版本、OpenAPI、用户操作手册、迁移和边界说明；旧证据标历史。
- 生成完整系统ZIP和仅变更文件补丁；不包含数据库、令牌、账号密码或venv。

## 执行结果
S1–S5已在本包实现。实际证据见05_VALIDATION_AND_BOUNDARIES.md。用户本机/线上部署、真实WMA、PostgreSQL和原生浏览器不属于已通过范围。没有新增运行时依赖，工具0.3.1源码未修改。
