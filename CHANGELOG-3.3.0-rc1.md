# DeepAha 3.3.0-rc1 · SG3

基于用户已人工验收通过的 SG2。

## Added

- Opportunity/Unit 当前性比较引擎；
- UPDATE_PENDING / missing / explicit withdrawal 精确语义；
- target history / version compare API；
- target-scoped manual withdrawal；
- target-scoped Direct WMA RECHECK；
- 审核页变化范围；
- 手机详情“有更新待收录”和版本记录；
- SG3 更正/延期/撤回/附件替换虚构体验包。

## Changed

- 更正只失效真正受影响的 Target/字段/提醒；
- 已知 deadline 发生变化时，旧日期不继续作为当前行动依据；
- rejected pending change 不自动恢复已取消的旧 deadline reminder；
- 明确 root withdrawal 才撤整个机会；明确 child withdrawal 只撤 child；
- adapter version 升级到 `overview-display/3.3.0`。

## Compatibility

- SG1 target identity contract 保持；
- SG2 multi-type Opportunity contract 保持；
- legacy revision 缺少 lifecycle metadata 时默认 ACTIVE；
- lifecycle metadata 不再泄漏成用户业务字段；
- SG3 无数据库 Schema migration。

## Not in SG3

Eligibility、个性排序、支付、外部通知、生产部署均未在本轮实现。
