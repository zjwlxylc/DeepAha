# Mobile R3 开发与验证报告

日期：2026-09-21。状态：完整源码工程候选，待用户/独立审查及目标环境验收。未push/merge/部署。

## 基线
本轮实际上传的R2完整ZIP，106,657,240字节，SHA256 `929ab1518f53717018864ffc7904600d9d8a4ca3f1bba52a776631e3dbb3f467`。先独立解压运行原产品测试：288项，286通过、2跳过。未用另一GitHub版本替代。基础产品版本保留3.8.0-rc1，本轮扩展 mobile-r3-services-20260921，最终前端 `mobile-r3-7f6388bb22f0`。

## 已完成
R2原应用内接入订阅服务、套餐/价格/项目管理、版本化订单与有效期、同事务定制申请和荐源、网站线索审核与原来源/任务适配、持续跟踪、原消息/未读和个人导出清理、服务Worker周期检查、OG公开元信息、两种品牌封面及安全上传、微信签名/缓存和可点击落地页。普通用户与工作台共用原会话和导航，不是iframe或第二个登录系统。

升级、源包、恢复也已接线：显式backup-first upgrade-services；原SQLite→目标数据库复制纳入14张会员表；复制后逐表行数和内容指纹核对；恢复后暂停服务运行开关。旧自动服务器安装器对R3阻断，避免复用错误目录或schema失败后启动旧worker。部署需使用本轮手册，不能声称已服务器一键验收。

## 实际验证记录
| 验证 | 结果 | 当前证据 |
|---|---|---|
| 当前完整product测试集 | 328通过、2跳过、0失败、0错误，共330项 | evidence/services-r3/final-verification/product.xml |
| S1复用业务/边界/历史装配测试 | 112通过、0跳过 | evidence/services-r3/final-verification/membership.xml |
| 每个product测试文件独立解释器 | 47个文件均退出0，含明确跳过的PG专项 | evidence/services-r3/per-file-final/per-file.json |
| 构建、编译、前端与HTTP阶段 | 14个阶段退出0 | evidence/services-r3/final-verification/verification.json |
| 真实回环TCP/HTTP | 81项通过 | evidence/services-r3/final-verification/http/http-smoke.json |
| 原R2页面与操作回归 | 115项通过，84页面×宽度组合 | evidence/services-r3/r2-browser-final/browser-r2.json |
| 新订阅、荐源、管理、分享设置 | 101项通过，28项布局尺寸记录 | evidence/services-r3/release-browser/browser-r3.json |
| 公开分享落地DOM/JS | 7项通过 | evidence/services-r3/share-browser-final/share-browser.json |
| LOGO/三海报及关键业务保护 | 16个文件与上传R2字节相同 | evidence/services-r3/protected-files.json |

浏览器合计223项检查通过，无页面JavaScript错误。以上是具体场景验证，不是所有设备、所有可访问性标准、渗透或业务准确率认证。当前测试基于已有Linux/Python3.13.5/Node22.16环境；完整版本见environment.json。本轮明确pypdf>=5.9,<7兼容范围，没有将原环境的5.9伪装为6.x；没有执行Windows全新依赖安装。

## 新边界测试实际覆盖
同一个登录cookie/CSRF下角色与数据隔离、免费用户不能创建付费跟踪、不同有效期/名额、金额与条款快照、重复请求、原未读与合并消息、清理时取消队列且不重建私人记录、账号停用/订阅到期在远程创建前阻断、上传任务资料后撤销在prompt前阻断、真实Product+模拟WMA客户端从队列到候选/整体审核/发布通知、同事务定制申请+网站提交的错误回滚、非公开目录仍可登录访问原应用但不泄露OG、撤回内容不能分享旧标题、固定外部签名地址和凭据缓存、签名去片段、错误脱敏、限频和轮换、位图上传/重编码/尺寸/越权。

真实宿主WMA模拟客户端测试调用原worker和原审核发布，不是手工在目标机会表塞一行充当端到端。供应商传输仍为模拟，不计作真实WMA调用。Node分享脚本用模拟SDK验证15项行为，也不计作微信客户端成功。

## 初始失败和修正没有删除
01/02/03/04/06阶段在功能缺失时记录失败；随后实现并复跑。05宿主跟踪发现响应返回时私人记录已清理的竞争窗口，改为返回CANCELLED、不恢复记录；真实队列仍取消。07发现禁公开目录不应连已登录用户的原应用HTML一起挡掉，改为仅分享页拒绝、原应用noindex。08发现旧迁移未纳入会员表，补齐复制及恢复暂停。

一次前端命令从错误cwd执行，保留initial-cwd.log，改为web目录后全部复跑成功。R3构建脚本第一版只打印纯函数结果、未写manifest，修改页脚后ASSET_BUILD_STALE正确阻止启动，导致初始逐文件/浏览器运行失败；已修正构建写入并重新执行47个文件和原页面回归。初始per-file目录是失败历史，不作为通过证据。独立复跑另发现一条历史测试仍精确要求旧-experience1后缀，按新schema代际改为更完整的-experience1-services1，单独复跑通过；原失败和复跑日志均保留，未放松跨代际回退禁止。

## 环境与交付边界
Chromium原生本地导航返回ERR_BLOCKED_BY_ADMINISTRATOR，原失败在browser-native；未修改管理员策略。浏览器采用明确测试桥：实际生产DOM/ES模块和真实本地FastAPI/SQLite通过桥交互。它不证明原生导航、Cookie/TLS、Service Worker、微信内核、实体触控/软键盘。

未执行：真实PostgreSQL数据库/备份恢复、真实WMA供应商、真实微信账号/客户端、微信/支付宝收款、Windows实机、实体Android/iOS、独立第三方安全/无障碍审查。套餐默认草稿、服务运行关闭，未产生真实付费调用。自检不等于独立审查，合并发布需用户验收。

最终ZIP另外重新解压到新目录做CRC、文件清单核对和完整测试。事后复验结果写在外部PACKAGE_RECEIPT，避免自校验包内嵌入关于自己的循环校验；最终以该回执为准。

首次打包清单误用字典格式，原verify_manifest工具拒绝；已改回继承的files数组/file_count/bytes格式，重新打包，不交付被拒绝的包。
