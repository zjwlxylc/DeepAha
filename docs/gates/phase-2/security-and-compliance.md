# Phase 2 安全与合规

## 已实现边界

- 默认 pytest marker 排除 `integration` 与 `live_source`，CI 不设置 live 权限。
- live 必须显式设置 `DEEPAHA_ALLOW_LIVE_SOURCE_CHECK=true`，只允许 Registry active host、
  有界 GET、30 秒超时、最多三次尝试和至少 6 小时间隔。
- host 经过允许列表和 DNS/IP 安全检查；不绕过登录、验证码、付费墙或技术限制。
- 十个中国官方 Endpoint 均为 `LINK_ONLY` 且 `fixture_storage_allowed=false`。
- runner 外部摘要不保存 response body、header、cookie、凭据或对象内容。
- HTML 禁用网络与外部实体；PDF/XLSX 在解析前执行大小、加密、页数、宏/外链等限制。

## 当前审查状态

本地测试与已提交 fixture 未包含中国官方网页完整响应、数据库、对象存储内容或真实用户数据。
GOV.UK HTML 依 OGL v3.0 单独核验并保留署名。最终精确候选提交的 scope、秘密和跟踪产物扫描
尚未完成，远程 CI 也尚未检查，因此本文件不是 Gate 关闭结论。
