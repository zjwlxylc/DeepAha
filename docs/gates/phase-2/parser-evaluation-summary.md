# Phase 2 解析器评估摘要

## 已验证固定样本

| 解析器 | 固定输入 | 实际 locator | 结果 |
| --- | --- | ---: | --- |
| lxml HTML | 合成边界样本及 69,317-byte GOV.UK OGL HTML | 官方样本 28 | locator 全部从原始字节回放并匹配文本 SHA。 |
| pypdf PDF | 880-byte 两页文本 PDF；另有 549-byte 危险样本 | 两页样本 2 | 页码/字符区间回放通过；危险/无文本/加密/超限路径有审计失败。 |
| openpyxl XLSX | 5,552-byte 确定性工作簿 | 4 | sheet/range/cell hash 回放通过；公式按公式文本读取，外部链接与宏边界受限。 |

固定输入 SHA：

- GOV.UK HTML：`b7b92f5e24f496bf462aeb6669cd117fbc83d2f691d6bf2a42024085a58d3468`
- 两页 PDF：`9773c35a9b32b46af4e810e2a8cc690f5c949dfa7ba1a9874335d8a94f0923c2`
- XLSX：`eace0d5c0bd4d5cd36cbadc8657928040e1fe7a42ffa3ddefeb0ea8c00e4b4e7`

定向 contracts/sources/documents 测试实际为 148 个通过。该结果只证明固定输入上的确定性、
安全边界和 Evidence Locator replay，不证明业务字段抽取准确率、OCR 能力、全国来源覆盖率
或真实机会价值。
