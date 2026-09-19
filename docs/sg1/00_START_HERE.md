# SG1｜先看这里

本版本完成 **SG1 可行动机会粒度**：保留“父公告 / 根 Opportunity”作为一次整体审核、版本、证据和历史上下文；把真正可以独立浏览、收藏、提醒、反馈和后续资格判断的 **POSITION / TRACK / PROGRAM_TIER / REGION_VARIANT** 物化为机会总览的基本单元。

## 你本地这份真实数据会发生什么

你上传的 RC2 数据副本中，当前只有：

- 1 个根公告 Opportunity；
- 1 个 Publication；
- 1 个整体审核 Decision；
- WMA 返回结构中 58 个 GROUP 单位组；
- WMA 返回结构中 106 个 POSITION 岗位。

SG1 升级后保持前 3 项不变，同时新增：

- 164 个 Unit identity（58 GROUP + 106 POSITION）；
- 106 个 Catalog Target；
- 机会总览显示 106 个具体岗位，不显示 58 个 GROUP，也不再用父公告充当主卡片。

## Windows 本地复现

1. 先停止正在运行的旧 RC2。
2. **不要删除或移动** `C:\Users\LENOVO\deepaha-data`。
3. 把本代码包解压到一个新的程序目录；不要覆盖唯一代码副本。
4. 双击根目录 `启动机会星图.cmd`（若解压工具把中文脚本名处理异常，也可执行 `py -3.13 scripts\launch_product.py --install`）。
5. 启动器会检测旧 RC2 数据库，先生成 SG1 备份，再新增 Unit / Catalog Target 表并回填；不会重新调用 WMA。
6. 打开 `http://127.0.0.1:8000/app/overview`。
7. 你的这份数据应显示 **106 项机会**，卡片主标题应是具体岗位，例如“服务类专业教师”“思政专业教师”，而不是只有一张“浙江省省属事业单位2026年下半年集中公开招聘人员公告”。
8. 打开任一岗位详情，应分别看到：岗位内容、单位/分组共同内容、公告共同条件，以及父公告入口。

自动备份默认位于：

`C:\Users\LENOVO\deepaha-data\backups\before-sg1-*.zip`

## 本版本没有做什么

- 没有进入 SG2；
- 没有把整体收录解释成资格已核实；
- 没有恢复旧逐字段审核/方法认证路线；
- 没有重新调用 WMA；
- 没有实现完整 AI 匹配；
- 没有改动你上传的原始数据库和 objects，本轮验证只操作副本。

详细证据见 `05_REAL_WMA_VALIDATION.md` 与 `evidence/sg1/`。
