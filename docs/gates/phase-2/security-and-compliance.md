# Phase 2 安全与合规

## 已实现边界

- 默认 pytest marker 排除 `integration` 与 `live_source`，CI 不设置 live 权限。
- live 必须显式设置 `DEEPAHA_ALLOW_LIVE_SOURCE_CHECK=true`，只允许 Registry active host、
  有界 GET、30 秒超时、最多三次尝试和至少 6 小时间隔。
- host 经过允许列表和 DNS/IP 安全检查；不绕过登录、验证码、付费墙或技术限制。
- Endpoint 与每次重定向 URL 均禁止 `user:password@host` 用户信息，避免隐式 Basic Auth
  和凭据跨 host 外传；Pydantic、JSON Schema、Registry 与 collector policy 测试共同约束。
- 十个中国官方 Endpoint 均为 `LINK_ONLY` 且 `fixture_storage_allowed=false`。
- runner 外部摘要不保存 response body、header、cookie、凭据或对象内容。
- HTML 禁用网络与外部实体；PDF/XLSX 在解析前执行大小、加密、页数、宏/外链等限制；XLSX
  不信任 worksheet 声明维度，按实际 XML 单元格流式遍历，防止伪造维度造成资源耗尽。

## 2026-08-22 实际扫描

| 检查 | 实际结果 |
| --- | --- |
| `uvx pip-audit --strict`（backend） | 未发现已知漏洞。 |
| `uvx bandit -r src -lll -ii`（backend） | 未发现符合阈值的问题；3,513 行代码，严重度/置信度计数均为 0。 |
| `corepack pnpm audit --prod --registry=https://registry.npmjs.org`（web） | 未发现已知生产依赖漏洞。此前 Next.js 16.2.11 路径中的 2 个 moderate、3 个 high 已由 `ed0bf33` 升级到 16.3.2 消除。 |
| 184 个 tracked candidate 的数据库/缓存/构建产物模式扫描 | 0 命中。大于 1 MiB 的 9 个文件均为 Phase 2 起点前既存的 `设计/*.png`；94 个 Phase 2 候选变更文件中此项为 0。 |
| `password/secret/token/cookie/authorization/api-key` 关键词复核 | 命中均为安全边界代码、负向测试、依赖名、文档或 disposable 本地测试常量。 |
| 私钥、AWS/GitHub/OpenAI key、Bearer、JWT 高风险模式 | 0 命中。 |
| fixture 许可与范围 | 只有合成文档及带 manifest/OGL v3.0 归属的 GOV.UK 固定 JSON/HTML；没有中国官方网页响应。 |

## 当前审查结论

本地测试与已提交 fixture 未包含中国官方网页完整响应、数据库、对象存储内容或真实用户数据。
GOV.UK HTML 依 OGL v3.0 单独核验并保留署名。代码审查修复提交 `5779b61` 的远程 CI
[32518043724](https://github.com/zjwlxylc/DeepAha/actions/runs/32518043724) 已成功；此前实现管线
`64b09f5` 与 Web 安全更新 `ed0bf33` 的远程 CI 也成功。

DNS 检查与 HTTP 客户端二次解析之间仍有 TOCTOU 窗口；当前只接受受版本控制、人工核验的
固定官方 Registry host。live runner 还要求单写者操作。两项边界详见[代码审查](./code-review.md)。
Gate 关闭前仍须对 live 后形成的精确最终候选重新执行 scope/secret/artifact 扫描、新鲜副本和
远程 CI，因此本文件不是 Gate 关闭结论。
