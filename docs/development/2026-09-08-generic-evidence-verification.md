# 通用 Evidence 核验：批次 A

根据用户指定任务“通用Delivery 验证器设计”的[架构结论](D:/DeepAha/docs/development/reviews/2026-09-08-evidence-verification-architecture-review.md)，从已合并 PR #10 的主线 `22b9cb8` 继续实施。采用薄层通用核验，不建设第二套文档理解系统；完整顺序见[实施计划](../superpowers/plans/2026-09-08-generic-evidence-verification.md)。

## 本批实现

- `evidence_verification/contracts.py / registry.py / verifier.py` 定义原件、Reader 身份、可追溯文本投影和公共字面核验。结果分别记录内容存在、声明定位、Reader 文本位置绑定、精度、歧义及 PASS/FAIL/UNVERIFIED。注册表仅接受本地代码；历史回放精确选择 Reader 身份，不默用最新版。
- HTML/PDF/XLSX Adapter 读取固定字节并解释对应范围。一次运行对每份原件与 Reader 身份只读取一次，读取失败也缓存；核验内核没有格式、事实字段或资格分支。新增合成格式只需 Adapter、注册配置和测试。
- HTML `html-quote-c14n/1` 与有界 Excel 读取从 Delivery 搬到共享组件；旧 Delivery 的调用签名和判定路径保留。新版 HTML Reader 单独启用截断/编码丢失检查，不改变历史解析器默认行为。
- 结构分隔与原有空格分开。只有明确选择的 HTML 单元格内 Han 字符之间的 p/br 人工折行可连接；跨行、跨格、原有空格、否定词、日期、大小写及兼容字符不折叠为相同文字，不使用语义匹配。

原文坐标是**固定版本 Reader 读取后的文本节点、PDF 文本层或单元格字符坐标**，不是原文件字节偏移或 PDF 像素。HTML 节点路径由既有清理后的 DOM 重放；比较投影偏移独立保存。每个匹配记录原件 Hash、Reader/比较版本、表示与投影 Hash、原始 quote/locator 和来源范围；相同原位置的段落/单元格视图去重，不把重复位置任选为通过。

本批是影子调用。`binding=BOUND` 仅表示本 Reader 已取得唯一可追溯文本位置，**不表示数据库 EvidenceRef 已建立或事实已批准**。DocumentBlock/EvidenceRef 的一次性兼容扩展、正式绑定接线和审核页面属于后续批次 B/C，尚未完成；旧回执、Candidate Facts、Schema、V3 Prompt 与模型配置不变。

## 验证与评审修复

本地后端全套非集成测试 **1277 passed / 467 deselected**，其中新组件 98 项；完整 Linux/Windows mypy **405 文件 / 0 错误**，Ruff 检查与 436 文件格式检查通过。数据库和 Web 无行为接线改动，本地没有重复执行上一批数据库或浏览器矩阵；提交候选仍由现有远程 CI 运行完整矩阵。日志见 `evidence/2026-09-08-generic-evidence-*`。

独立评审提出的六项问题已建立反例并修复：

1. 读取不完整/不可靠时“未找到 scope”不能证明定位错误，保留 UNVERIFIED 和未建立定位。
2. HTML 过深导致 libxml 截断时，新 Reader 不返回完整表示。
3. PDF 含未读取图像、Form 内图像/内联图像、绘图或注释时，整页范围保留不完整；已有文字可以 FOUND，但不能证明整页 PASS 或 NOT_FOUND。没有增加 OCR 或图片解码，此保守边界也适用于带装饰图形的 PDF。
4. 坏 XLSX 的 shared string 越界和损坏 XML 转为读取失败，避免中断整批验证；没有吞掉所有程序异常。
5. 仅 BOM/空白的段落不创建零长度来源范围，不影响其他合法段落。另以固定种子覆盖 2000 组文字与节点拆分，比较投影与既有 c14n 一致。

6. XLSX 单元格保留公式/布尔/错误类型及非字面数字格式的歧义标记；未读取缓存显示值时不能以未命中证明引文错误，也不计算公式。标记仅影响相应 cell/row，不污染其他普通单元格。

独立只读复核确认六项 P2 均可关闭、无遗留 P2 及以上问题，结论限于本批影子路径。候选 CI 状态随后追加，不把本地验证写成正式发布资格。

## 冻结真实案例

[逐条影子结果](evidence/2026-09-08-generic-evidence-shadow-replay-final.json)和[可复现脚本](evidence/2026-09-08-generic-evidence-shadow-replay.py)使用原六个文件，不下载、不调用 WMA、不写业务数据库。旧实现与新影子结果均为 **94 PASS / 0 FAIL / 30 UNVERIFIED**，逐条旧 PASS 回归数为 0。

- 四个 `学历、学位要求` 引用自然通过，来源映射分别指向同一单元格的两个文本节点，长度 4 与 3。
- 内联 `site_publish_time` selector 命中实际内联节点，不受旧叶块粒度限制。
- 30 条 binary DOC 未注册生产 Reader，仍为 UNVERIFIED。先前独立 Word 读回的内容命中记录保留，但不伪装为本 Reader 的 FOUND/绑定或清除 `human_verify`。
- 六份原件 Hash 不变，当前 Delivery 仍为 **UNVERIFIED**；没有发现新的真实 Agent quote 错误。

首次影子 JSON 及 `-reviewed.json` 保留为中间记录；`-final.json` 对应六项修复后的源文件 Hash。它们是同一个公告的重复工程回放，不是新增独立调查样本。
