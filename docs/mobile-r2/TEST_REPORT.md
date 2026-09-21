# Mobile R2｜开发与自检报告

状态：完整源码工程候选，自检通过的范围如下；用户尚未验收 R2，未提交远程仓库或部署。

## 1. 基线和实现边界

父包：DeepAha_84353c7_体验改善_完整源码_20260920.zip。SHA-256：`e378d7abbf4f6a23f640eeb730aab6f9b82a42601283a991f4cd6e8fc91d7b60`。用户在对话中确认父包人工测试通过。本轮从该包建立独立副本，未跟随 Codex 进行中的 main/发布变动。继承的历史提交为 84353c7e5286e276d24af8e0342d4d3441c30ec5，不把 R2 伪装成一个新远程提交。

前端指纹：`mobile-r2-c8d459040dd2`。产品基础版本仍为 3.8.0-rc1；迭代标识 mobile-r2-20260920。本轮新增数据库表 0，保留父版本 experience1 的5张扩展表和全部现有数据。资格、价值排序、整体审核、Scout及WMA远程调用边界未重写。

## 2. 最终实际执行结果

| 验证 | 结果 | 证据 |
|---|---|---|
| 当前完整 product 测试集 | 286通过、2跳过、0失败、0错误，共288项 | evidence/mobile-r2/final-verification/product.xml |
| 按文件、独立解释器再运行 | 39个测试文件均返回0；包含有明确跳过的PG文件 | evidence/mobile-r2/per-file-final/per-file.json |
| 指纹、Python编译、JS语法/业务契约及HTTP检查 | 12个命令阶段全部成功 | evidence/mobile-r2/final-verification/verification.json |
| 真实本地HTTP | 62项通过 | evidence/mobile-r2/final-verification/http/http-smoke.json |
| 主浏览器回归 | 115项通过，其中84个页面×宽度组合及31项交互等检查 | evidence/mobile-r2/release-browser/browser-r2.json |
| 追加定向操作回归 | 13项通过 | evidence/mobile-r2/focused2-green/focused.json |
| 请求丢失/失败、短视口及权限场景 | 11项通过 | evidence/mobile-r2/edges-fixed/edges.json |
| 本地相同原件并发保存 | 3项真实文件锁测试通过；20轮合成双任务全部完成、没有存储异常 | test_mobile_r2_storage.py；evidence/mobile-r2/concurrent-rerun.json |
| 品牌/核心文件保护 | 17个受保护文件字节不变 | evidence/mobile-r2/protected-files.json |

普通用户测试覆盖13个页面在320、390、768、1440像素下的52种组合；审核/管理16个页面在390、1440像素下的32种组合。截图使用合成数据，不包含真实用户画像或凭据。浏览器主回归未发现 JavaScript 页面错误、页面级横向溢出。不能将这些定点检查扩写为所有设备或全部无障碍标准达标。

2项跳过都是需要真实PostgreSQL环境的专项验证，不计作通过。没有启动真实 WMA Worker 或请求供应商。合成并发结果仅验证本地调度/存储机制，不解锁任何生产并发能力。

## 3. 端到端与故障验证到底覆盖什么

页面模块通过浏览器DOM/JS执行，读写接口指向独立SQLite和真实本地FastAPI。实际验证了登录、机会筛选及返回、已有行动状态读取、幂等收藏、持续准备清单、画像保存/冲突合并、消息、退出、角色权限与来源/任务/审核筛选上下文。

额外模拟的是网络故障，不是业务结果：其中一个场景由后端实际保存成功后，测试桥丢掉响应；页面必须保留输入，后续同一请求键重试不得新增第二条。短视口为390×500，并非实体手机键盘测试。清除个人数据后再次进入画像也验证未从内存草稿恢复被清除的资料。

## 4. 未通过/中断的初始记录，不冒充绿灯

首次基线全测在约73项时被工具200秒执行时限中断；未计为通过。一次初始浏览器长流程也被执行时限终止，后续改为独立进程保存完整日志。

本轮首次新增测试失败记录保存在 red-api、red-js、red-layout、red-asset-validation、focused-red、focused2-red 和 red-storage 等证据中。修正后分别重跑并纳入最终回归。

最初验证脚本在仓库根目录无显式目标递归收集，误收集旧归档及命令行工具：终端记录197个收集错误，JUnit含198条错误记录（含内部退出），其中旧 test_library_dialog_dom.py 需要 --input/--output，收集时退出。未把该轮标为通过。完整错误名在 evidence/mobile-r2/initial-discovery-failure/collection-errors.json。最终验证明确限定项目当前产品测试目录 backend/tests/product，与当前 pyproject 的产品测试入口对齐；没有据此宣称所有历史项目测试均通过。

按文件复跑首轮发现 test_dispatch_policy.py 的双任务用例1项失败。随后在第3轮独立复现实验中取得真实堆栈：LocalFileObjectStore 的非阻塞锁报 Resource temporarily unavailable。产品存储层增加最多2秒、仅限该忙锁错误的等待；不修改底层原件完整性校验，不重发模型。保留原失败、诊断栈、失败先行的新测试及绿色复跑。

追加故障脚本首次在恢复 fetch 时错误地返回函数，Playwright自动求值导致QA桥空URL异常；修正为不返回值的赋值语句，再执行11项全绿。此错误未进入生产代码。

## 5. 环境限制

当前为已有 Linux / Python 3.13.5 / Node22.16 环境，不是 Windows。pypdf实装5.9.0，而项目声明6.x：R2未改变解析器，但本次不能称为规范依赖的全新安装验收；请在目标环境按 requirements 安装后重跑。其余实际版本见 evidence/mobile-r2/environment.json。

管理策略阻止 Chromium 原生 URL 导航，尝试返回 ERR_BLOCKED_BY_ADMINISTRATOR。本轮未改动浏览器策略；采用明确标注的测试专用 HTTP bridge 加载真实页面模块并连接本地服务。因而浏览器结果不证明原生导航、Cookie/TLS、Service Worker、真实离线网络或生产HTTPS行为。HTTP层独立检查缓存、版本目录、权限与CSRF。

未执行：原生 Windows 新安装、真实 PostgreSQL迁移/恢复、真实 WMA单任务或2/4并发、实体Android/iOS触控/软键盘、安全渗透、完整无障碍认证、真人D1与生产发布。作者自检不等于独立审查。

## 6. 实际压缩包复验

交付时对最终ZIP进行CRC检查、重新解压到新目录、逐文件SHA-256核对，再在重新解压目录执行指纹、完整product测试、HTTP与前端命令验证。为避免在自校验包里写入事后记录，实际结果另附 PACKAGE_RECEIPT.json 与“重解压验证记录”文件；以该回执为最终打包复验证据，而不是本段文字自行宣称通过。

## 7. 发布前人工复核

先等待Codex对父版本发布结束，再按 CHANGESET_MOBILE_R2.json 作三方比较，不能整包覆盖main。重点检查：真实手机上首页海报和详情操作条、返回/输入键盘、资料冲突、已有收藏进度、准备清单连续编辑、来源与任务筛选、首次从旧缓存切换。现场服务名/端口/指针以当前正式部署为准。
