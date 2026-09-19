# SG6.2 最终验证记录

## 产品回归

最终源码树 `backend/tests/product` 共 **21 个测试文件 / 202 项测试**。每个测试文件均在独立 pytest 进程执行并获得 `RC=0`，0 failed。

SG6.2 专项：

- `test_qualification_compiler.py`: 19 项；
- `test_sg6_2_frontend_contract.py`: 3 项；
- `test_sg6_2_upgrade.py`: 3 项。

SG4 Eligibility 17 项、SG5 Value/Priority 13 项全部保持通过。

## 前端与编译

- `check-product.mjs`: PASS
- `check-sg5.mjs`: PASS
- `check-sg5-1.mjs`: PASS
- `check-sg6.mjs`: PASS
- `check-sg6-1.mjs`: PASS
- `python -m compileall backend/src/deepaha/product`: PASS

## 真实数据库升级

从用户上传数据的副本重新执行：

1. 第一次 `upgrade-sg6-2`：backup verified，328 Target refreshed；
2. 第二次：`already_current=true`，`targets_refreshed=0`，`data_modified=false`；
3. Opportunity / Identity / Unit / Decision / Publication / Revision / Snapshot / Task / Account / Profile 等旧权威表逐行摘要不变；
4. object store 252 个文件聚合 SHA-256 前后一致：
   `3a6a65a223ce371d80976fddcb6efcc3ea80f4b063fb4cd4780efe307778ff54`。

## 老路线防回归

- 当前 reviewer 写入口仍只有整包 `/api/review/{id}/decision`；
- 旧 `/api/v1/review/*` 写入口继续返回 `410 ROUTE_RETIRED`；
- 没有新增字段批准 API、字段审核页面、VerifiedFact/Rule 人工晋升动作；
- `upgrade-sg6-2` 只写 CatalogTarget 派生 compiler metadata + Meta 版本，不写事实/规则。

## 环境边界

未执行 PostgreSQL 实机迁移；Windows 本机浏览器体验仍由用户完成。SG6.2 不需要重新调用 WMA。
