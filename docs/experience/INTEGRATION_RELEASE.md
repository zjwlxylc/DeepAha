# Experience 集成发布记录

本次来源为 `D:\DeepAha_Experience`，基于 main `84353c7e5286e276d24af8e0342d4d3441c30ec5`。用户已完成本地人工验收，明确授权迁移到 `D:\DeepAha`、提交、推送 main 并部署正式站。

原包 2,724 个清单文件全部哈希校验通过，全部迁入，不删除原有文件。保留用户验收的业务与界面实现；集成阶段仅补齐产品运行依赖 `pypdf==6.19.0`，增加 `ops/experience/release.py` 以执行本版五张表迁移与安全回退。

正式服务仍为 `deepaha-api@staging` / `deepaha-worker@staging`，8100；隔离 staging 为 `staging-isolated`，8200。隔离 staging 验证后恢复停止、disabled 的按需启动状态。不可用旧版部署脚本跨数据库代际回退 Worker。

本地验证及实机回执分别保存于 `D:\DeepAha-experience-release` 和服务器 `/var/backups/deepaha/experience/<build>/`。后续以本文件附录及回执为准，原包 TEST_REPORT 等 NOT_RUN 状态属于打包时历史。

已完成：本地全量 276 通过、2 项 PostgreSQL opt-in 在专用实机临时库另行全部通过；本机原生 Chrome 87 个页面/尺寸组合无溢出、无 JS 错误；29 项真实 HTTP 检查通过。37 个测试文件独立执行均 RC=0（PostgreSQL 文件本地 opt-in 跳过，在宿主另测）；compileall 和六项 Node 检查通过。正式上线回执待后续附录。

生产存在一条原有 NEEDS_RECOVERY/COLLECTING 任务。发布不修改其结果、不自动重发；迁移为它保留 remote_pending 占用，须由维护员按实际远端状态执行回收/确认结束。未做真实 WMA 并发验证，保持默认串行。

发布器会停止写入、备份数据库和 objects、在独立空库恢复演练、核对旧行内容哈希，之后切换不可变目录。若切换失败，恢复旧 API，升级过数据库后不自动启动旧 Worker；不以备份覆盖正在使用的数据库。

集成时统一 Git 文本换行为 LF（保留既有按原始字节锁定的 WMA 契约例外），避免 Windows 工作目录与 Git archive 的 FILE_MANIFEST 哈希不一致。
