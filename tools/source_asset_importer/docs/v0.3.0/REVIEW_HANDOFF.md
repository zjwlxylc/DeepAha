# 后续独立代码复核清单

范围：原v0.2.0到本v0.3.0的增量；不改DeepAha主仓，不连接生产库，不启动WMA。

阅读顺序：README → DESIGN → COMPATIBILITY → VALIDATION → FEEDBACK_PLAN。代码重点：research/ingest、audit、baseline、workspace、library、feedback；workbench；web。

请独立复核：
1. 原Package/ImportService/权限/事务逻辑是否未放宽，研究包是否不会偷偷进入旧执行接口。
2. ZIP边界、路径、大小/CRC、重复JSON字段、namespace、同run冲突是否fail closed；新格式未识别不能当成功。
3. 候选归并是否保留版本/原件，Brief和附件是否能回到同namespace的实际条目，跨生产者同URL是否只有提案。
4. 基线是否实际比较selected字节与链，永久旧缺口是否不掩盖新故障，是否有虚构first_seen/系统回执。
5. 本地意见撤销/并发/导出是否一致，导出原件SHA是否重新核验，部分审核是否明确。
6. HTTP是否回环绑定、Host/Origin/令牌一致，无任意本机路径/命令入口；Codex调用是否只按明确配置和受选文件，不伪造原件或读取无关账号。
7. 系统反馈是否始终把格式与真实性分开；无法自填PRODUCTION升级官方状态。
8. 使用Windows真实启动、多文件/ZIP、关闭重开、浏览器实际下载；在用户授权且Codex确有Library工具时验证真实取回。缺权限如实报错，不修改浏览器策略绕过。

运行 `python -m unittest discover -s tests -v`，GUI测试需要显示环境；Linux可用xvfb-run。不要把旧样本里的演练回执当真实系统反馈。主系统接入按FEEDBACK_PLAN里的R2任务走，库/运行时版本以实际HEAD为准。

本文件是下一次复核请求，不是已经完成独立审查的证明。
