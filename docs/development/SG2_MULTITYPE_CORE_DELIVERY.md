# SG2 Multi-type Opportunity Core Delivery

## GOAL

在 SG1 已验收的 Root → Unit → Catalog Target 基础上，让招聘/实习、竞赛、科研、奖学金、人才政策/补贴、升学/夏令营、成长实践共享同一个 Opportunity Core，并保持类型语义、scope、unknown 字段和行动目标正确。

## STATUS

`SG2_IMPLEMENTED_LOCAL_ACCEPTANCE_CANDIDATE`

本状态不是用户人工验收，也不是生产 Release Qualification。

## IMPLEMENTED

- 新增多类型 presentation contract：`opportunity_core.py`；
- 支持 `PROGRAM_TIER / REGION_VARIANT / DEFAULT_SINGLETON` 的稳定前台语义；
- 支持旧 `units/positions/tracks/children` 与新 `program_tiers/region_variants/action_units`；
- actionable frontier：有更具体可行动后代时不重复发布父 actionable unit；
- 非招聘 GROUP 不再误当发布方；
- unknown fields 完整保留并可全文搜索；
- Unit 可覆盖自己的 region/summary/application_url/official_url；
- 子级精确行动日期只有在证据引用支持同一日期时才采用；
- 多类型手机端文案、筛选、详情、父级上下文；
- 6 个虚构、明确标记的本地体验包；
- 中文旧 WMA 类型别名兼容。

## SG1 REGRESSION

用户上传的原始真实 WMA 数据副本重新从 RC2 状态执行 SG1 backup-first 投影：

- Root Publication: 1
- Overview Decision: 1
- GROUP: 58
- POSITION: 106
- Catalog Target: 106
- 第二次升级：`already_current=true / data_modified=false`

SG2 不增加数据库迁移，不改变这 106 个招聘目标。

## SG2 REPRESENTATIVE GATE

自动回归覆盖：

1. 招聘；
2. 竞赛；
3. 科研；
4. 奖学金；
5. 人才政策/补贴；
6. 升学/暑期项目；
7. 通用成长实践 action_units 契约。

## UI EVIDENCE

隔离虚构数据浏览器桥接验收：

- 五类筛选可见；
- 竞赛使用赛道/赛事规则语义；
- 滚动政策无假 deadline；
- 奖学金未知字段可搜索；
- 升学项目档次可见；
- 360/390/430px 无横向溢出；
- page errors = 0。

容器 Chromium 原生 loopback 仍受管理员策略限制，故使用与 SG1 相同的显式 HTTP bridge；业务请求仍真实进入 FastAPI + SQLite 隔离库。

## NOT IMPLEMENTED / STOP LINE

- SG3 当前性、更正/延期/撤回的 unit-level 精确影响；
- SG4 Eligibility；
- SG5 AI ranking / Value / Priority；
- 支付、订阅、机构后台；
- 真实多类型 WMA 新采集。

**停止在 SG2，等待用户人工验收。**
