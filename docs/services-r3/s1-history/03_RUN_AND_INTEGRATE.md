# 运行、接入与运维说明

## 1. 本机演示：最短路径
Windows 解压后运行根目录 `Start_Demo.cmd`。也可在 PowerShell 中逐条执行：
```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m deepaha_membership.demo --data .demo --port 8765
```
浏览器打开 `http://127.0.0.1:8765/membership`。每次启动生成新的随机密码，旧会话失效；订单和设置保存在 `.demo/demo.db`。同一演示进程内模拟来源/任务状态有效，重启后模拟队列内存不保留，不能用于真实运营。重新体验全流程时使用一个新的演示目录，例如 `--data .demo-second`。

本机演示严格只监听127.0.0.1。它不是给手机直接访问的局域网服务器，更不是公网认证服务。可在电脑浏览器的设备模拟中看手机布局；真实移动浏览器需要完成宿主HTTPS接入后验收。

依赖中包含tzdata，避免Windows没有IANA时区数据而无法计算北京时间。Python官方说明：https://docs.python.org/3/library/zoneinfo.html#data-sources 。本次仅在Linux/Python3.13.5执行测试，没有运行Windows批处理。

## 2. 推荐体验顺序
先以 maintainer 登录，进入“服务管理→套餐价格”，核对三种草稿套餐再上架。切换 alice，申请基础订阅；再由 maintainer 在“申请与报价”选择“赠送试用”，最后回到 alice 查看服务周期并新增跟踪主题。

网站流程用 bob 演示：先申请定制、等待维护员填写报价、由 bob 确认，再由维护员赠送试用。bob 提交公开网站，reviewer 整体通过；bob 在网站建议中加入定制跟踪；maintainer 登记来源、明确启用，再到跟踪任务安排和交接。演示提供“模拟结果返回”，只会转为“已有结果·等待整体审核”，不会伪造正式发布。

主题检查按钮会从合成公开目录生成真实站内消息。用户输入的网页不进行真实抓取。本机体验中“人工核对开通”仅用于理解真实上线的财务核对流程，不应填写真实账号/付款隐私。

## 3. 生成精确R2整合候选
先取得原始R2压缩包，不要重新压缩或把main改名代替。组装命令：
```powershell
py -3 tools\assemble_r2.py --baseline "D:\项目包\DeepAha_Mobile_R2_完整源码_20260920.zip" --output "D:\项目包\DeepAha_R2_S1_UNVERIFIED.zip"
```
工具会先核对整个ZIP的SHA-256、拒绝危险路径/符号链接/重复大小写路径、检查唯一API接入锚点，再在临时副本中加入模块。原文件只有 `backend/src/deepaha/product/api.py` 增加挂载语句；其余原文件按内容指纹复核不变。不会写数据库、覆盖本地工作树或部署。

如果报“锚点不兼容”“缺少R2清单”或哈希不一致，应停止自动组装，让开发者基于真实代码做小范围接入；不要删除这些检查。工具的成功路径仅对合成R2结构运行过测试，真实R2包尚未实跑。

候选包中新增 `MEMBERSHIP_ASSEMBLY.json`、`membership-addon` 与后端包副本。旧R2指纹清单保留作为历史，不可继续当作新候选整包的验收证明。

## 4. 候选副本安装
在隔离分支与预生产环境，保留原Python环境与启动方式。安装候选中的附加项目：
```powershell
python -m pip install .\membership-addon
```
模块使用原 Product 数据库引擎，新增表均以 `mbr_` 开头。不会通过网页GET或应用启动隐式建表。访问路径 `/membership`，接口前缀 `/api/membership`。

### 显式初始化
停止应用和所有写入/采集worker，先按项目原流程备份数据库、对象文件和配置。本工具只负责数据库备份步骤，不替代完整项目备份。

已有SQLite宿主数据库可使用：
```powershell
$env:MEMBERSHIP_DATABASE_URL = "sqlite:///D:/DeepAha/data/product.db"
python -m deepaha_membership.cli init --backup "D:/DeepAha-backups/member-before-20260921.db"
```
也可在原项目环境用 `init --from-core --backup ...` 读取原Settings。SQLite会生成新备份、执行完整性检查、先写备份回执再建会员表；不会覆盖已有备份。数据库连接串不要放进截图、报告或日志。

PostgreSQL路径目前要求先提供原运维流程生成的非空备份文件；本模块只记录其字节指纹，不证明备份可恢复。**未完成PostgreSQL预生产恢复演练和会员迁移测试之前，不应在生产执行该初始化路径。**

结构不完整或写锁记录缺失会明确拒绝运行，不自动修复或删除历史表。升级失败后保留现场和备份回执；按原项目恢复流程恢复数据库与代码，不能仅回退代码后继续对新库写入。

## 5. 周期任务：先只做轻量检查
本包不自动安装系统定时任务，不在网页进程里偷偷启动线程。
```powershell
python -m deepaha_membership.cli tick --operator "原系统中的维护员账号"
```
默认仅检查已发布主题/网站机会、回读已有任务状态，不创建新的WMA任务。账户权限从原数据库重新核验。

在预生产完成真实源和成本验收、并明确授权后，才可配置包含下列参数的周期命令：
```powershell
python -m deepaha_membership.cli tick --operator "原维护员账号" --allow-site-enqueue --max-jobs 3 --connection default
```
建议宿主调度器每小时调用一次，但每条跟踪仍受其快照间隔控制：基础公开目录24小时、深度/定制公开目录6小时、定制网站调查默认24小时。`--max-jobs`是每次命令上限，不是全平台每日预算；总费用/并发/连接治理继续交给原WMA调度策略。返回不明确的任务不自动无限重试，应由原授权维护员核查后重试同一任务。

以上给出的是调度接入方式，并未在用户服务器安装或启动任何计划任务。CLI与实际R2的集成未验收。

## 6. 必须完成的宿主接入清单
- 核对 Product.authenticate、角色继承、CSRF、来源默认启用行为、BindingRegistry、任务幂等、CatalogTarget/Identity/Meta 数据模型与本适配器一致。
- 原导航“个人服务/我的订阅”增加会员入口；审核区增加“用户网站线索”入口，不把它当作机会发布审核。原Logo与三海报保持不变。
- 原消息中心需要合并会员消息或明显链接到新增消息页，不能让用户以为消息丢失。本次采用独立会员消息页，未改原消息表。
- 原个人数据导出/清理、账户停用与账号重建政策需要纳入会员记录处理。目前新增数据按原用户名关联，不能在未处理历史记录时把同名账号重新分配给另一个人。
- 原自由文本机会反馈不会自动解析任意URL；本次已实现的是明确的“网站建议”入口。旧反馈入口要补上引导/选择公开网站表单，不应把所有粘贴链接直接当采集授权。
- 核对SourceProfile新来源默认状态与宿主调度策略。本模块登记时不主动改变原登记返回的启用状态；来源显式启用和实际任务授权另外操作，不宣称原有来源调度会自动停止。
- 完成全套R2回归、真实浏览器同源会话/CSRF/HTTPS、真人手机、PostgreSQL、真实WMA来源/附件、费用与失败恢复验收。

这些是尚未完成的整合工作，不是已经实现的上线能力。

## 7. 测试复现
```powershell
python -m pip install ".[test]"
python -m pytest -q
node --check src/deepaha_membership/static/app.js
```
浏览器检查是可选开发依赖，需要另行安装Playwright与浏览器：
```powershell
python -m pip install playwright
python tools/browser_check.py --chromium "本机Chromium或Chrome可执行文件路径"
```
脚本会记录原生导航结果，并明确使用QA桥接模式检查DOM/JS与本地HTTP。它不能替代真实浏览器原生网络链路验收。

## 已核对的原来源默认值与本地授权门
2026-09-21读取的main快照中，SourceProfile.scheduling_enabled默认为True、interval_hours默认为0。这不构成R2实际运行验收。为避免原默认状态被误当作定制任务授权，本模块另有collection_enabled门，初始为False；只有维护员明确启用本模块来源后才可交接网站任务。不会仅因登记来源或原来源已经启用而跳过此授权。
