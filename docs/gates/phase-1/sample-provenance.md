# Phase 1 官方样本来源与许可

## 固定捕获

| 字段 | 固定值 |
| --- | --- |
| 请求 URL | `https://www.gov.uk/api/content/government/news/civil-service-fast-stream-named-uks-top-graduate-employer` |
| 解析 URL | `https://www.gov.uk/api/content/government/news/civil-service-fast-stream-named-uks-top-graduate-employer` |
| 公开来源页 | [Civil Service Fast Stream named UK's top graduate employer](https://www.gov.uk/government/news/civil-service-fast-stream-named-uks-top-graduate-employer) |
| 抓取时间 | `2026-08-21T09:59:08.005Z` |
| HTTP 状态 | `200` |
| 媒体类型 | `application/json; charset=utf-8` |
| 原始字节数 | `11662` |
| SHA-256 | `1589f9177e197a578c8d37bd5a3bc869a17d7b0936f156666f69a2f88fbb9d2b` |
| bucket | `deepaha-raw` |
| object key | `raw/sha256/15/1589f9177e197a578c8d37bd5a3bc869a17d7b0936f156666f69a2f88fbb9d2b` |
| 公共存储 URI | `s3://deepaha-raw/raw/sha256/15/1589f9177e197a578c8d37bd5a3bc869a17d7b0936f156666f69a2f88fbb9d2b` |
| collector | `phase1_design_capture/0.1.0` |
| 元数据契约 | `0.1.0` |

实施时对固定 API URL 做了新鲜 GET；实际返回仍为 HTTP 200、相同媒体类型、11,662 字节与相同 SHA，且最终 URL 未变化。仓库保留的是已确认捕获时间的固定响应，不把实施时复核时间改写成新的抓取事实。

## 官方主体与许可

响应标识 Government Skills 与 Civil Service Fast Stream 两个官方组织。GOV.UK 条款说明大多数内容受 Crown copyright 保护并按[开放政府许可 v3.0（Open Government Licence v3.0）](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)发布，完整边界见 [GOV.UK terms and conditions](https://www.gov.uk/help/terms-conditions)。

归属声明：

> Contains public sector information licensed under the Open Government Licence v3.0.

## 明确限制

- 该样本不是 Gold 业务样本，不证明抽取准确率、机会覆盖率或商业价值。
- 该英国样本不证明中国或浙江首发来源覆盖。
- 新闻稿不证明 Fast Stream 当前仍可申请；Opportunity 因此使用 `UNKNOWN`、`INTERNAL`、`current_version=null`。
- Document 的发布时间来自固定响应 `2025-09-17T00:00:00+01:00`，等价 UTC 为 `2025-09-16T23:00:00Z`；不得写成另一个 UTC 时间。
- 仓库没有复制响应中链接的图片、Cookie、响应头或第三方资产。JSON 中的外部 URL 只是原始响应字节的一部分。
