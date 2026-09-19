# 本地验收

- product测试：31个文件逐一独立执行，31/31 RC=0；新增账号准入测试9项。
- 含SG7.1资格、推荐两套独立Gold Oracle，SG8-A SQLite typed-copy迁移harness及部署静态契约。
- compileall、product和SG7.2前端契约、access-ui.js语法、git diff --check通过。
- 真实本地HTTP及Chrome：管理员发码、移动端注册、user权限拒绝、一次性重置码与重新登录通过；JavaScript错误0。
- 目视检查：移动端注册说明/同意控件和桌面用户管理可用，已修正新控件与既有CSS的冲突。
- Windows环境：静态测试显式解析PATH的Bash路径，以免CreateProcess先找到不可用的System32 WSL启动器；验证使用Git Bash。

完整运行日志保存在本机 `D:\DeepAha-beta-access-work`。这些是工程验收，不是真实用户研究证据。
