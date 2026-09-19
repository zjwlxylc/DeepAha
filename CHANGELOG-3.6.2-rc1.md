# DeepAha 3.6.2-rc1 · SG6.2 Qualification Evidence Compiler

SG6.2 在 3.6.1-rc1 / SG6.1 上补齐「WMA 候选资格事实 → 可计算资格条件」的自动编译链。SG1–SG6.1 已验收业务语义继续冻结；本版本不进入 SG7。

## 核心变化

- 新增 `Qualification Evidence Compiler`：中英文/别名字段统一到 canonical qualification condition。
- 扩展可确定性编译：学历、学位、国籍、政治面貌、工作年限、证书/职称/语言、参赛对象、团队人数等。
- 扩展 EvidenceResolver：继续支持 HTML/TXT/XLSX，并增加 DOCX、可读文本 PDF、与原件哈希绑定的派生 OCR 文本。
- 新增 coverage / unresolved / qualification risk 输出；不把未解决条件隐藏掉。
- `INELIGIBLE` 仍只允许由「当前正式内容 + 已定位 Evidence + 可确定性硬条件 + 明确冲突」产生。
- 对 Evidence 尚不足、但画像与候选条件存在明显确定性冲突的机会，正式 Eligibility 仍保持 `UNCERTAIN`，但 SG5 标记 `HOLD_FOR_CONFIRMATION` 并退出稀缺 headline Top-N。
- 画像增加学位、学业状态、国籍、政治面貌、工作年限、证书、职称、语言证书、团队人数等可选字段；只用于 DeepAha 本地确定性核对，不发送 WMA。
- 新增 backup-first `upgrade-sg6-2`，只刷新可重建的资格编译派生投影；Windows 启动器自动接入。

## 明确没有做

- 没有恢复逐字段人工审核、逐岗位字段确认、规则审批或 scope approval。
- 没有让 WMA 自己批准 VerifiedFact / Rule / Eligibility。
- 没有用 LLM/Embedding 猜测硬资格。
- 没有为了降低 UNCERTAIN 强制解析「相关专业」「符合其一」「特殊例外」等长尾语义。
- 没有运行时 OCR 猜扫描 PDF；没有绑定到保存原件的 OCR 派生文本时继续 fail closed。

## 真实数据结果

在用户上传的 328 个当前 Target 快照上：

- `requirements = 0`：189 → **0**；
- 完整测试画像：300 UNCERTAIN / 28 INELIGIBLE → **185 UNCERTAIN / 139 INELIGIBLE / 4 LIKELY_ELIGIBLE**；
- 类用户画像（专科 + 宁波）：97 INELIGIBLE / 231 UNCERTAIN → **199 INELIGIBLE / 129 UNCERTAIN**；
- 其中 100 个扫描型 PDF 岗位因没有可验证的 hash-bound OCR 派生文本保持 `UNCERTAIN + HIGH RISK`；
- 该画像的 SG5 headline `featured` 从 3 个错误的 `UNCERTAIN + HIGH` 机会变为 **0**；高风险项仅留在“资格待核对 / 继续探索”。

这不是“判断率越高越好”的优化；保留下来的不确定性是系统明确无法安全裁决的部分。
