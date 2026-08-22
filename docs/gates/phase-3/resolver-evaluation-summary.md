# Phase 3 Resolver 合成评估摘要

## 数据集

- 文件：`backend/tests/fixtures/opportunities/phase3-resolution-cases.json`。
- 许可/性质：`CC0-1.0 synthetic fixture`，无业务事实。
- 固定字节 SHA-256：`1ab32974f7dc982bb6cf12b8d023a53b136136b1c254779003b789734d8f7f82`。
- 9 个 case：`CREATED` 1、`LINKED` 6、`NEEDS_REVIEW` 2。

主路径覆盖重复公告、正文+附件、岗位表、更正、延期和取消；保守路径覆盖强键冲突与弱指纹
误合并保护。成功主路径形成 6 个 Version/Event：CREATED、两次 ATTACHMENT_REPLACED、
CORRECTED、DEADLINE_CHANGED、CANCELLED；纯重复公告只增加审计 link，不产生版本。

## 结论边界

固定样本证明实现对这些字节和场景具有确定性，并能在两套全新数据库得到相同语义输出。
它不证明真实世界 precision/recall、`>=95%` 变更识别率、全国来源覆盖或无人维护能力；不得把
9/9 固定断言换算为生产准确率。默认测试不访问实时站点、浏览器或模型。
