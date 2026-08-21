# Phase 1 官方证据样本

本目录只保存 Phase 1 契约与原始证据纵向验证所需的一份固定响应：
`civil-service-fast-stream-news-2025.json`。它来自 GOV.UK Content API，对应的公开来源页面是
[Civil Service Fast Stream named UK's top graduate employer](https://www.gov.uk/government/news/civil-service-fast-stream-named-uks-top-graduate-employer)。

响应标识的两个官方组织（official organisations）是 Government Skills 与 Civil Service Fast
Stream。固定捕获的请求 URL、抓取时间、媒体类型、字节数、SHA-256、许可和限制写在同名
manifest 中。fixture 必须按原始 UTF-8 字节读取，不得格式化、重排或用解析结果覆盖。

## 许可与归属

GOV.UK 条款说明其大多数内容按[开放政府许可 v3.0（Open Government Licence
v3.0）](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)发布；完整边界见
[GOV.UK terms and conditions](https://www.gov.uk/help/terms-conditions)。归属声明：

> Contains public sector information licensed under the Open Government Licence v3.0.

本仓库没有复制响应中链接的图片或其他第三方资产；JSON 中的外部 URL 只是原始响应字节的一部分。

## 使用限制

- 该样本用于证明契约、不可变原始字节、去重和证据定位，不是 Gold 业务样本。
- 该英国样本不证明中国首发范围的来源覆盖。
- 新闻稿证明的是公开原文及其发布事实，不证明 Fast Stream 当前仍可申请，也不应据此生成资格或业务结论。
