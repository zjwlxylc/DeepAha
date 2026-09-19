# SG4 本地验收入口

SG4 目标：在 SG1–SG3 已通过的具体 Opportunity Target 上，安全回答 **“我现在能不能参加？”**。

## 正式数据

已经通过 SG3 的 `C:\Users\LENOVO\deepaha-data` 不需要迁移。停止旧版后直接用本包运行 `启动机会星图.cmd`。机会总览应继续保持 106 个真实岗位。

登录后进入 **我的 → 我的关注方向**，可以补充：学历、专业、专业代码、毕业年份、出生日期、户籍地区。打开任一具体机会，点击 **“适合我吗”**。

SG4 不给匹配百分比。页面只显示：

- 当前条件明确符合 `ELIGIBLE`
- 当前已知条件基本符合 `LIKELY_ELIGIBLE`
- 暂不能完整判断 `UNCERTAIN`
- 发现明确不符合条件 `INELIGIBLE`

每一条可计算条件都可以展开“查看资格依据”。

## 虚构四态体验

不要污染正式库。使用单独目录：

`C:\Users\LENOVO\deepaha-data-sg4-test`

使用 `examples/sg4-eligibility/` 中 4 个 ZIP。先登记来源：

- 名称：海湾研究中心（虚构）
- URL：`https://research.example.org/`

建议画像：本科、广告学、专业代码 050303、毕业年份 2027、出生日期 2004-06-01、户籍 浙江省宁波市。

预期：E01=ELIGIBLE、I01=INELIGIBLE、U01=UNCERTAIN、L01=LIKELY_ELIGIBLE。

## 验收重点

1. I01 的学历与专业冲突必须能展开看到保存 XLSX 的 Sheet/Row/Column；
2. U01 不能因为“看起来不符合”而被判 INELIGIBLE；
3. 关闭或不填写画像字段时应增加待确认，而不是自动否定；
4. SG3 `UPDATE_PENDING` 的受影响字段不能用于最终资格否定；
5. 真实 106 岗位数量和父公告整体审核不变。

SG4 人工通过前不进入 SG5。
