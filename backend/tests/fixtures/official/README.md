# Phase 1–2 官方证据样本

本目录保存两份指向同一 GOV.UK 新闻页的固定响应：Phase 1 使用 Content API JSON，Phase 2
使用页面 HTML 原始响应 body。文件分别是 `civil-service-fast-stream-news-2025.json` 与
`civil-service-fast-stream-news-2025.html`。对应的公开来源页面是
[Civil Service Fast Stream named UK's top graduate employer](https://www.gov.uk/government/news/civil-service-fast-stream-named-uks-top-graduate-employer)。

响应标识的两个官方组织（official organisations）是 Government Skills 与 Civil Service Fast
Stream。固定捕获的请求 URL、抓取时间、媒体类型、字节数、SHA-256、许可和限制写在同名
manifest 中。fixture 必须按原始 UTF-8 字节读取，不得格式化、重排或用解析结果覆盖。

Phase 2 HTML 于 2026-08-21T16:39:17.809Z 重新核验并通过一次有界 HTTPS GET 捕获。响应为
HTTP 200、`text/html; charset=utf-8`、69,317 bytes、SHA-256
`b7b92f5e24f496bf462aeb6669cd117fbc83d2f691d6bf2a42024085a58d3468`。只保存响应 body；
未保存 header、cookie、外部图片或其它页面资产。详细捕获元数据写在
`civil-service-fast-stream-news-2025-html.manifest.json`。

## 许可与归属

GOV.UK 条款说明其大多数内容按[开放政府许可 v3.0（Open Government Licence
v3.0）](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)发布；完整边界见
[GOV.UK terms and conditions](https://www.gov.uk/help/terms-conditions)。归属声明：

> Contains public sector information licensed under the Open Government Licence v3.0.

本仓库没有复制响应中链接的图片或其他第三方资产；JSON/HTML 中的外部 URL 只是原始响应
字节的一部分。OGL 不授予第三方权利，也不允许暗示官方背书；使用者仍须遵守归属、第三方
权利、无背书和“按原样”限制。

## 使用限制

- 该样本用于证明契约、不可变原始字节、去重和证据定位，不是 Gold 业务样本。
- 该英国样本不证明中国首发范围的来源覆盖。
- 新闻稿证明的是公开原文及其发布事实，不证明 Fast Stream 当前仍可申请，也不应据此生成资格或业务结论。
