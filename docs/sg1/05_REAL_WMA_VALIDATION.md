# SG1 真实 WMA 数据复现记录

日期：2026-09-18

## 输入边界

使用用户上传的 `deepaha-data.zip` 的**隔离副本**。原始数据库与 `objects/deepaha-raw` 不做写操作。数据库中的 Task `files` 字段继续通过内容哈希定位原件。

## 升级前观察

- Root Opportunity：1
- Publication：1
- Overview Decision：1
- Task：1
- `product_opportunity_units`：不存在
- `product_catalog_targets`：不存在
- WMA 投影：58 个单位 GROUP + 106 个 POSITION，共 164 个结构分项

## SG1 backup-first 升级结果

`python -m deepaha.product.cli upgrade-sg1`

结果：

- `backup_verified = true`
- `catalog_targets_created = 106`
- `product_opportunity_units = 164`
- `product_catalog_targets = 106`
- 106 个当前 Target 全部为 `POSITION`
- 58 个 GROUP 仅作为 scope，不进入机会总览

备份 SHA-256：

`9af74a0ac9e97715fe33994398b36f508037185eeef3b9f1385ecb0bdf12e211`

## 原数据未改写证明

升级前后以下旧表逐行序列化摘要一致：

- `product_opportunity_identity`
- `product_overview_publications`
- `product_overview_decisions`
- `product_tasks`
- `product_result_snapshots`
- `product_overview_revisions`

Task 所引用 9 份 WMA 文件在原数据与升级副本中的 SHA-256 均与数据库记录一致，包括 `report.md`、`opportunities.json`、`evidence.json`、招聘计划 XLSX、应聘指南 DOC、HTML 与派生文本。

## API 真实回读

登录隔离副本后：

- `/api/review/{revision}`：父公告 / 根机会 1 项；全部结构分项 164；预计进入总览的具体机会 **106**。
- `/api/catalog?limit=3`：`total = 106`。
- 样例岗位：编号 106，“服务类专业教师”，单位“浙江省机电技师学院”，地区“浙江义乌”。
- 岗位详情分开返回 `fields`（岗位自身）、`ancestor_fields`（单位/分组）、`common_fields`（父公告共同条件）。

## 浏览器交互验证

当前执行容器的 Chromium 访问 loopback 被管理员策略阻止，因此使用项目既有的 **explicit HTTP bridge**：浏览器仅负责渲染/交互，所有业务请求仍实际发送到运行中的 FastAPI + SQLite 副本，没有模拟业务响应。

已验证：

- 已收录审核详情显示 106 个行动目标；
- 总览显示 106 项岗位卡；
- 搜索“服务类专业教师”定位编号 106；
- 岗位详情存在岗位 / 单位共同 / 公告共同三层内容；
- 360 / 390 / 430 px 无横向溢出；
- 收藏编号 106 后“我的行动”只出现该具体岗位；
- 页面脚本错误 0。

截图和机器记录见 `evidence/sg1/`。

## 验收结论

`SG1_PASS`（本地 SQLite + 用户上传真实 WMA 数据副本范围）。

尚未由本轮证明：Windows 本机真实浏览器、全新环境联网安装依赖、PostgreSQL、线上部署、真实后续 WMA 新版本身份延续、SG2 及之后的资格/推荐质量。当前容器无外网，`--install` 无法从 PyPI 获取 `codebuddy-cloud-agent-sdk==0.3.4`；这不影响已安装依赖环境中的 93 项后端测试、真实 SQLite 回填和 API/浏览器桥接验证，但不能冒充 Windows 首次安装验证。这些不属于 SG1 PASS 的冒充范围。
