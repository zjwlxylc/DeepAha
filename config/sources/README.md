# Phase 2 Source Registry

`phase2-official-endpoints.json` 是来源注册表（Source Registry）v0.2.0 的首批策略清单。它记录的是 2026-08-21 当日逐项核验后的采集候选，不把端点长期可用性、内容许可或 Gate 指标写成永久事实。

## 使用边界

- 10 个端点均为官方公开入口，默认采集器只允许有界同步 HTTP GET；不绕过登录、验证码、JavaScript 挑战、付费墙或其他访问限制。
- 最小访问间隔为 21,600 秒（6 小时），每次最多 3 次尝试、单次超时 30 秒，浏览器策略为 `NEVER`。
- 所有端点均采用 `LINK_ONLY`：原始对象可以作为本地受控证据保存，但不得把响应正文、对象存储内容或中国官方网页固定样本提交到仓库，也不得公开复制全文。
- 没有找到这些页面适用的明确开放许可，因此全部 `fixture_storage_allowed=false`。GOV.UK OGL v3.0 固定样本是 Task 10 的独立许可路径，不改变本清单。
- robots 返回 4xx 时按 [RFC 9309 section 2.3.1.3](https://www.rfc-editor.org/rfc/rfc9309.html#section-2.3.1.3) 记录为 `NOT_APPLICABLE`；robots 明确存在时只启用未被禁止的路径。连接超时、5xx 或无法判定不会被记为允许。

## 2026-08-21 核验记录

核验时间统一记录为 `2026-08-21T15:26:28Z`。核验只读取最终 URL、状态、媒体类型、大小和 robots 规则；未把响应正文保存到仓库。

| 角色 | 实际入口 | 结果 | robots / 使用判断 |
| --- | --- | --- | --- |
| 国家公务员局 | `http://bm.scs.gov.cn/pp/gkweb/core/web/ui/business/home/gkhome.html` | `200 text/html` | 同主机 `/robots.txt` 为 403，依 RFC 9309 记 `NOT_APPLICABLE`；主站 `www.scs.gov.cn` 已不可作为静态列表，改用同一权威域的 2026 国考专题 |
| 人社部招聘 | `https://www.mohrss.gov.cn/SYrlzyhshbzb/fwyd/SYkaoshizhaopin/zyhgjjgsydwgkzp/` | `200 text/html` | `/robots.txt` 为 404，`NOT_APPLICABLE` |
| 国资委招聘 | `http://www.sasac.gov.cn/n2588035/n2588325/n2588350/index.html` | `200 text/html` | robots 仅禁止 `/sd`，目标路径 `ALLOWED`；HTTPS 在核验网络超时，清单保留实际成功的 HTTP URL |
| 中国政府网政策 | `https://www.gov.cn/zhengce/zhengceku/bmwj/home.htm` | `200 text/html` | robots 未禁止目标路径，`ALLOWED` |
| 教育部资助 | `http://www.moe.gov.cn/jyb_xxgk/xxgk/neirong/fenlei/sxml_cwysj/cwysj_xszz/xszz_zzbg/` | `200 text/html` | HTTPS 实际重定向为同主机 HTTP；robots 为 404，`NOT_APPLICABLE` |
| 共青团青年发展 | `https://www.gqt.org.cn/notice/index.htm` | `200 text/html` | robots 为 404，`NOT_APPLICABLE` |
| 浙江人社 | `https://rlsbt.zj.gov.cn/col/col1229743683/index.html` | `200 text/html` | robots 为 404，`NOT_APPLICABLE` |
| 浙江人事考试 | `http://www.zjks.com/` | `200 text/html` | robots 为 404，`NOT_APPLICABLE`；`gwy.zjks.gov.cn` HTTPS 在核验网络超时，保留固定角色要求中的当前可达官方主机 |
| 浙江科技 | `https://kjt.zj.gov.cn/col/col1229225203/index.html` | `200 text/html` | robots 为 404，`NOT_APPLICABLE` |
| 浙江教育 | `https://jyt.zj.gov.cn/col/col1229266336/index.html` | `200 text/html` | robots 为 404，`NOT_APPLICABLE` |

策略发生任何语义变化时必须使用新的 `policy_version` 和 `endpoint_id`。相同 `(source_id, url, policy_version)` 的不同含义会由导入器以 `SOURCE_POLICY_CONFLICT` 拒绝；清单加载不会展开环境变量。
