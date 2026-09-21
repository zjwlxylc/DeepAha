# Mobile R2｜运行、升级与交接

## 使用哪个版本
本包是用户已验收的 experience-84353c7-20260920 之上的第二轮产品体验迭代，标记 mobile-r2-20260920。不是交互原型、不是只含修改文件的补丁。底层产品版本号暂保留 3.8.0-rc1；正式 Git 提交/发布标签由 Codex 合入时确定，不冒充一个已经存在的远程提交。

## Windows 本地继续使用
先在当前本机服务窗口按 Ctrl+C，等旧服务停止。将完整 ZIP 解压到一个新的文件夹，避免覆盖运行中的代码。保留上一版文件夹，并备份现有 deepaha-data。然后双击新版文件夹中的“启动机会星图.cmd”。启动器会显示程序目录和 mobile-r2 开头的前端版本，再执行原有兼容性检查。

也可在源码根目录的 PowerShell 运行：
```powershell
py -3.13 scripts/launch_product.py --install
```
程序数据默认仍在用户目录下的 deepaha-data，或你原先显式指定的 DEEPAHA_DATA_DIR。R2 不迁移、不复制、不清空原数据库，也不改变已有账号口令。已经成功完成上一轮 experience 升级的数据库，本次不新增表；控制台仍检查 SG1 / SG5.1 / SG6 / SG6.2 / SG7 / experience，是兼容检查，并非加载了旧界面。

新目录首次运行可能需要准备专用虚拟环境；本轮未在原生 Windows 全新安装依赖，依赖版本以 backend/requirements-product.txt / pyproject.toml 为准。不要将本地启动器用于生产 PostgreSQL。

## 前端版本与缓存
JS 与 CSS 使用同一内容指纹目录 `/product/_v/mobile-r2-.../`，相对导入的子模块自然继承目录。HTML 与 API 不缓存，旧兼容资源地址要求重新验证。启动时会核对文件与指纹，不匹配则提示 ASSET_BUILD_STALE，避免同一“不可变版本”对应不同源码。

修改任何前端 JS、CSS 或 index.html 后，在源码根目录运行：
```powershell
py -3.13 scripts/mobile_r2/build_assets.py
py -3.13 scripts/mobile_r2/build_assets.py --check
```
不要只给 app.js 手工添加查询参数。部署后查看 `/api/site` 的 frontend_build、HTML 的版本目录和静态响应的 X-DeepAha-Build。旧的页面已经打开时，新响应会提示有新版可用；先保存输入再刷新。不强行自动刷新正在编辑的页面。首次从旧固定地址版本过渡时，仍可能需要一次强制刷新。

## 自检命令
以下命令均从源码根目录执行，使用独立合成数据，不启动 WMA Worker：
```powershell
py -3.13 scripts/mobile_r2/verify.py --output evidence/local-r2
py -3.13 scripts/mobile_r2/per_file.py --output evidence/local-r2-per-file
py -3.13 scripts/mobile_r2/browser_check.py --transport native --output evidence/local-r2-browser
py -3.13 scripts/mobile_r2/browser_check.py --transport native --focused --output evidence/local-r2-focused
py -3.13 scripts/mobile_r2/browser_check.py --transport native --edges --output evidence/local-r2-edges
```
浏览器测试需要 Playwright 与 Chromium。`--chromium` 可指定本机浏览器可执行文件。当前交付环境只能使用显式测试桥，因此本机优先执行 native；不要为了测试更改企业浏览器安全策略。故障注入脚本只在测试中模拟请求失败，生产代码不含测试桥。

验证 product 测试应显式传入 backend/tests/product；不要在仓库根目录对历史归档和各种 CLI 脚本做无参数递归收集。历史工具拥有各自的运行参数与依赖，本轮未重新验收全部历史项目。

## 数据与回退边界
R2 相对已验收 experience1 父版本，新增表为 0；收藏与准备仍保存到上一轮已有表。累计 RELEASE_COMPATIBILITY.json 保留 schema_change_in_release=true 和禁止自动回退的安全锁，这是因为整个包仍包含 experience1 相对早期版本的五张表及新调度语义。新增字段 iteration_schema_change=false 表达 R2 本身没有再改表。

需要回退时先停本轮 API/Worker，确认没有进行中任务，再由维护员切回已验收的 experience1 同代代码。保留当前数据库和原件，不把旧备份直接覆盖当前业务库，不跨代自动回退到前 experience 的 Worker。回退前端应刷新页面，不能要求旧 API 提供 R2 新端点。

## 给 Codex 的集成注意事项
本轮没有读取或改写 Codex 正在部署的分支。先等待那次发布完成，再核对本包 CHANGESET_MOBILE_R2.json 的逐文件旧/新哈希，与仓库当前值三方比较。当前值不同于旧哈希时，必须检查冲突，不能整包覆盖 main。

生产服务名、端口、环境文件、当前指针、Nginx 与 Ops Gateway 配置以现场已验收状态为准。不要用历史模板覆盖现场，也不要因为目录中仍有 SG8-A 历史文档而重建账号、替换数据库或重新配置 WMA。发布前必须保留 staging、备份和人工验收；本轮没有部署授权执行结果。
