# DeepAha 机会星图｜Mobile R2

这是完整程序源码，不是HTML原型。以你人工验收的上一轮体验改善包继续迭代，侧重手机可读、好操作及避免误操作。正式LOGO与三张海报原样保留。

先读 docs/mobile-r2/RUN_AND_UPGRADE.md。变化清单见 CHANGELOG.md，自检与未测边界见 TEST_REPORT.md。给Codex的合入要求见 CODEX_HANDOFF.md。

本地：先停止旧服务，将本包解压到新目录，双击“启动机会星图.cmd”。保留原数据目录，不重置账号。控制台应显示 mobile-r2 开头的前端版本。R2不新增数据库表。

正式站：先等上一轮部署结束，再由Codex对照CHANGESET_MOBILE_R2.json核对冲突并验收；本包没有自动提交或部署。不要覆盖正在运行的目录、现有数据库、WMA密钥和现场服务配置。
