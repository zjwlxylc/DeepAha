# 首批 Direct WMA 调查底座集成

状态：已通过 PR #10 合入远程 main，合并 SHA `22b9cb8`。最终候选 `088afc2` 的 CI #74（run `34206716808`）九项全部通过；合并代码树与该候选一致。尚未部署或取得发布资格。起点为远程 main `9c8f5b2`。原开发分支 `codex/delivery1-direct-wma` 的后续功能保留，未整支合入。

## 本批范围

只接入内部调查登记、受控 WMA 执行、版本/会话检查点、原始字节回收、哈希/Schema/跨文件与引用检查、待审核记录、私有原件下载及内部材料审核。数据库迁移仅 `0035 / 0036`，承接主线 `0034`。

保留原件、原始 quote、未知字段和调查备注；支持可审计恢复，不以重跑模型代替文件回收。后续已经验证的中文 HTML 读取、表格/单元格定位及 `html-quote-c14n/1` 修复一并带入，避免合入已知旧缺陷。两条 openpyxl 可空值和一条 HTML locator 联合类型测试增加实际类型断言，没有关闭或放宽 mypy。

本批不包含后续实体登记、事实晋升、岗位规则、个人反馈、来源导入或新版用户首页。实际 WMA Prompt/SOP/Schema 和后台模型配置不修改，未增加实时调用；内部材料审核不批准正式事实或公开机会。

## 验证证据

| 项目 | 实际结果 |
| --- | --- |
| 全部非数据库后端测试 | 修复后 1179 passed / 467 deselected |
| 完整 mypy，Linux 与 Windows 目标 | 修复后两者均 389 files / 0 errors |
| 后端 Ruff / 格式 | 通过，420 个文件格式检查通过 |
| 前端全套 | 修复后 125 passed / 30 files；ESLint、TypeScript、生产构建通过 |
| 调查浏览器链 | 桌面与 390px 手机共 6 passed：原链路及登记/审核回执丢失重试；后端实际已提交，重试仍仅产生一条写入 |
| 相同真实交付离线核验 | Schema/跨文件 PASS；94 PASS / 0 FAIL / 30 UNVERIFIED；四条 HTML 表头 PASS；六个原始文件哈希不变 |
| 真实 PostgreSQL 18 / Moto 全套集成 | 修复后完整重跑 464 passed / 3 skipped / 1179 deselected。此前一轮唯一失败为测试桶名与 CI 不同；已改用 CI 桶名，未为该环境问题修改业务或测试断言 |
| 数据库迁移 | 空库到主线 0034 再到本批 0036、空测试库 0036→0034→0036 往返及 Alembic 模型一致性通过 |
| 独立只读代码审查 / 候选 CI | 三项 P2 已修复并通过独立复核 / PR #10 首轮 CI 暴露 Schema checkout 字节转换；修正后的最终候选 CI 九项全部通过 |

数据库使用本批新建的独立容器；没有操作用户已有业务库。浏览器使用实际 Next 构建和合成 API，实际 API/runner/数据库链由数据库集成测试覆盖；这些均不构成真人事实审核或真实 WMA 重复稳定性证据。

## 原始结果的状态

真实案例 `01a07fb6-4415-76bc-a14c-c6422b84cb0e` 的调查 COMPLETE 与 Delivery UNVERIFIED 分开。30 条二进制 DOC 原引用仍没有可执行定位规则，当前候选不将其自动通过。较长开发分支中独立 Word 读回和读取器选型材料保留。用户于本批过程中要求采用“通用Delivery 验证器设计”的架构方案，下一批优先统一版本化 Reader/Adapter、内容支持/绑定结果与公共证据边界，再按需接入 DOC；不在 Delivery 核心继续增加格式分支。

较长分支全量 mypy 的 863 条错误均在后续测试代码中，本批没有靠删除或忽略这些测试制造通过；它们对应的功能和迁移也没有带入本批，后续仍需逐批修复。

## 日志

证据文件位于本目录 `evidence/2026-09-08-intake-*`：后端/前端测试、Linux/Windows 类型检查、构建、浏览器、数据库迁移与离线回放分别保存。各自完整日志对应本批实际输入，不将不同运行次数累加为独立样本数量。

离线回放脚本：[脚本](evidence/2026-09-08-intake-offline-replay.py)、[逐条结果](evidence/2026-09-08-intake-offline-replay.json)。运行时将本工作树 `backend/src` 加入 PYTHONPATH，并显式传入原开发工作树的固定案例目录与已保存 baseline JSON；不复制或改写原件。

## 独立评审修复

提交 `6b587ee` 关闭三项 P2：

- 新版 HTML 使用自己的 DocumentBlock 契约，不再生成旧 0.2 回放器不能复现的 locator。P9B Parser 升为 0.8.2；旧 Lxml 0.2 行为及旧回放保持不变。
- XLSX 在展开前校验真实坐标和跨表累计资源预算。保护实际 relationship 目标，包括非 `.xml` 目标及重复物理表；保留合法稀疏坐标、零值和公式，不靠截断内容制造通过。资源拒绝不等于 Agent 引文错误。本批限制已复现的扩张路径，没有声称所有解析线程都可被强制中断。
- 登记/审核表单在第一次请求前已有随机请求标识；相同表单与内容重试复用后端幂等键，修改内容按新的操作处理。失败后保留输入和选择项，不把 React 的表单复位误当作用户修改。

独立复核只检查代码和合成内存样本，没有调用 WMA 或参与事实审批；确认无遗留 P2 及以上问题。浏览器最初额外发现选择项在 Action 返回后被原生 reset，已通过阻止自动 reset 修复；最终六个场景均通过。修复后的实际日志为 `evidence/2026-09-08-intake-review-fixes-*`；冻结原件逐条结果见[本次回放](evidence/2026-09-08-intake-review-fixes-replay.json)。旧日志保留用于说明验证经过，仅清理自动生成日志中的行尾空白。

## Linux CI 的原始 Schema 字节修复

PR #10 首轮 CI `34206238154` 中，backend-quality 的 101 个失败均受 `DELIVERY_SCHEMA_INTEGRITY_ERROR` 影响。Windows 工作区的两份外部 Schema 与固定 SHA 完全相同，但 Git 默认文本转换将入库 blob 改成 LF；Linux checkout 因此未取得约定的原始 CRLF 字节。

修复仅为这两份外部 Schema 设置 `.gitattributes -text`，将原本已在 Windows 工作区验证过的完整字节存入 Git。工作区 Schema 字节、JSON 字段/层级/枚举、固定 SHA 和校验逻辑均不变；没有对参与校验的数据做换行归一化。`git diff --check` 对这两个文件识别 CRLF 结尾，其他行尾空白检查保留。[Git blob 与原件哈希比较](evidence/2026-09-08-intake-schema-checkout.json)记录修复前后 SHA 及 JSON 契约不变断言。提交后需以新候选 CI 重新验收，不能使用旧 CI 通过部分代替。

## 合并记录

2026-09-08 经独立评审和最终 CI 后合并 [PR #10](https://github.com/zjwlxylc/DeepAha/pull/10)。[合并与九项 CI 回执](evidence/2026-09-08-intake-merged-ci.json)保存候选、主线和运行身份。用于本批集成的独立 PostgreSQL/Moto 容器已清理；用户根工作区和原开发分支保留。下一批从这一主线基线落实通用 Evidence 架构。
