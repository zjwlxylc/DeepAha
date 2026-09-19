# SG7 实施清单

## A. 数据层

- [x] 增加隔离 Lab 表；
- [x] 增加 schema version；
- [x] backup-first `upgrade-sg7`；
- [x] 幂等升级；
- [x] 不改生产事实/审核/WMA原件。

## B. Synthetic Twins

- [x] 100 个固定样本；
- [x] profile hash/version；
- [x] 多教育/专业/地区/目标/机会类型覆盖；
- [x] 不包含真实用户身份。

## C. Gold 与 Pair Truth

- [x] Production target snapshot → Lab Gold Case；
- [x] lock / retire；
- [x] 资格真值与推荐真值拆开；
- [x] human gold attestation gate；
- [x] locked truth 防覆盖。

## D. Benchmark

- [x] Catalog Safety；
- [x] Gold Benchmark；
- [x] `unsafe_recommendations`；
- [x] eligibility truth accuracy；
- [x] recommendation truth accuracy；
- [x] human gold / operator gold 分开计数；
- [x] `llm_used=false`、`production_mutated=false` 固化。

## E. Founding Users

- [x] 显式加入/退出；
- [x] 曝光只在 active consent 后记录；
- [x] 聚合 unknown/useful/action 指标；
- [x] 退出不影响主产品；
- [x] 隐私导出；
- [x] 隐私清除。

## F. 前端

- [x] operator `机会实验室`；
- [x] 普通用户 `机会共创实验`；
- [x] 100 Twin 状态；
- [x] Gold/Pair Truth；
- [x] Benchmark；
- [x] Founding metrics；
- [x] 明确“实验 ≠ 正式事实审批”。

## G. 回归

- [x] SG1–SG6.2 全产品测试；
- [x] SG7 专项测试；
- [x] 前端旧契约；
- [x] Python compile；
- [x] Real HTTP smoke；
- [x] 包内凭据扫描；
- [ ] 用户 Windows 人工验收。
