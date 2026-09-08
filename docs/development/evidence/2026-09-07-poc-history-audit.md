# PoC 历史运行只读审计（2026-09-07）

本次审计当前保存的 SQLite 与本地文件；没有导入 PoC 应用、运行 Verifier、联网或修改 PoC。数据库以 `mode=ro` 打开并启用 `query_only`。本地 run_id 保留用于定位；云 ID、密钥、联系方式、原文、引文和思考内容均未输出。

**结论：历史产物可复用为工程回归样本，不能作为正式事实或当前模型可用性的证明。**

| 指标 | 全部运行 | WMA（按 runner_kind） |
| --- | ---: | ---: |
| 数据库运行数 | 24 | 17 |
| 标记 COMPLETE | 24 | 17 |
| 完整三件套 | 17 | 14 |
| 旧 verdict：OK / NEEDS_REVIEW / 无回执 | 16 / 1 / 7 | 13 / 1 / 3 |
| 声明材料 / 可定位 | 93 / 90 | 78 / 78 |
| 字节 hash 相等 / 不等 / 缺 hash | 18 / 72 / 3 | 6 / 72 / 0 |
| 两份当前 Schema 均通过（仅结构） | 15 | 12 |
| 非空材料清单全部 hash 相等 | 1 | 0 |

数据库有 26 个 case、24 条 run；runner 分布为 WMA 17、workbuddy-cli 2、codex 1、未填写 4，未根据名字推断空值。三件套完整指两个 JSON 可解析且 report.md 非空，不表示内容充分。93 个声明条目中包含快照/派生材料，不能全称为已独立确认的官方原件。3 个不可定位条目均缺 local_path 和 hash；本轮没有打开越界路径或猜测替代文件。

## 全部 24 条记录

材料列依次为：声明 / 可定位 / hash 相等 / hash 不等 / 缺 hash。

| 本地 run_id | runner | 三件套 | 旧 verdict | 材料统计 |
| --- | --- | --- | --- | --- |
| `bs-competition#1` | workbuddy-wma | 完整 | OK | 8 / 8 / 0 / 8 / 0 |
| `bs-competition#2` | workbuddy-wma | 完整 | OK | 8 / 8 / 0 / 8 / 0 |
| `bs-entrepreneurship#1` | workbuddy-wma | 完整 | OK | 3 / 3 / 0 / 3 / 0 |
| `codex1#1` | codex | 缺失 | ABSENT | 0 / 0 / 0 / 0 / 0 |
| `interact-test#1` | NULL | 完整 | OK | 5 / 3 / 3 / 0 / 2 |
| `phase1-smoke#1` | NULL | 缺失 | ABSENT | 0 / 0 / 0 / 0 / 0 |
| `phase2-smoke#1` | NULL | 缺失 | ABSENT | 0 / 0 / 0 / 0 / 0 |
| `web-1788454943467#1` | workbuddy-cli | 完整 | OK | 3 / 2 / 2 / 0 / 1 |
| `wma-2026-1#1` | workbuddy-wma | 完整 | OK | 3 / 3 / 0 / 3 / 0 |
| `wma-2026-2#1` | workbuddy-wma | 完整 | OK | 9 / 9 / 2 / 7 / 0 |
| `wma-2026-3#2` | workbuddy-wma | 完整 | OK | 3 / 3 / 2 / 1 / 0 |
| `wma-smoke4#1` | workbuddy-wma | 缺失 | ABSENT | 0 / 0 / 0 / 0 / 0 |
| `wma-verify#1` | workbuddy-wma | 缺失 | ABSENT | 0 / 0 / 0 / 0 / 0 |
| `wma-zjhr#2` | workbuddy-wma | 缺失 | ABSENT | 0 / 0 / 0 / 0 / 0 |
| `wma-zjhr#3` | workbuddy-wma | 完整 | OK | 3 / 3 / 0 / 3 / 0 |
| `wma-zjhr#4` | workbuddy-wma | 完整 | OK | 3 / 3 / 0 / 3 / 0 |
| `zjhr-cli#1#1` | workbuddy-cli | 缺失 | ABSENT | 0 / 0 / 0 / 0 / 0 |
| `zjhr-live#1` | NULL | 完整 | OK | 7 / 7 / 7 / 0 / 0 |
| `zz-wma-2#1` | workbuddy-wma | 完整 | NEEDS_REVIEW | 3 / 3 / 0 / 3 / 0 |
| `zz-wma-3#1` | workbuddy-wma | 完整 | OK | 13 / 13 / 2 / 11 / 0 |
| `zz-wma-4#2` | workbuddy-wma | 完整 | OK | 1 / 1 / 0 / 1 / 0 |
| `zz-wma-5#1` | workbuddy-wma | 完整 | OK | 1 / 1 / 0 / 1 / 0 |
| `zz-wma-6#3` | workbuddy-wma | 完整 | OK | 4 / 4 / 0 / 4 / 0 |
| `zz-wma-7#1` | workbuddy-wma | 完整 | OK | 16 / 16 / 0 / 16 / 0 |

## 结构差异与复用边界

- 招聘 `wma-zjhr#4`：标准根对象，1 个单位、4 个岗位、42 个 Fact；旧回执 OK，但 3 个材料字节 hash 全不符。可保留结构用于候选映射回归，原材料完整性需要重新建立。
- 招聘 `wma-zjhr#3`：`opportunity` 包装层、`flattened_facts`、`entity_tree` 与当前两份 Schema 不兼容。当前保存回执实际已统计 51 条 Fact 且为 OK；代码注释记载的早期“零事实 OK”是历史事故说明，不能混成这份现存回执的实测值。
- 比赛 `bs-competition#1/#2`：同样用 units/positions 容器，但第二次 entities 把 3 个中层实体写成 track，9 个叶子实体写成 position；第一次为 3 个 unit、2 个 position。两次分别 42/118 个 Fact，材料各 8 个且全部 hash 不符。它们展示不同语义不能机械套招聘单位/岗位映射，也不能把数量差直接解释为质量提升。
- 政策 `bs-entrepreneurship#1`：一次性创业补贴被表示为 1 个 unit、4 个 position、46 个 Fact；此处 position 不能未经业务核验当作招聘岗位。3 个材料全部 hash 不符。可复用作政策结构边界案例，当前交付不据此扩品类。
- 大规模招聘结构样本 `wma-2026-3#2` 含 274 个 unit、300 个 position、3337 个 Fact；`zz-wma-2#1` 含 95 个 unit、232 个 position、6179 个 Fact。这些是模型产物计数，不是已验证真实机会数量或完整率。
- 产物存在 artifact_id/id、media_type/mime/file_type/content_type、标准根/包装层等差异。JSON 的 per-run schema_checks、structure 和逐材料字段状态支持精确定位；没有把宽松 Schema 通过当作可直接摄取。
- 非 WMA 对照 `web-1788454943467#1` 的标准嵌套位置仅有 22 条 Fact，facts_flat 有 33 条；交叉投影不一致，而旧回执仍是 OK。历史“能解析”不能替代双方实体与字段逐项一致。

## 旧 OK 为什么不足

当前 `app/services/verifier.py:177–182` 仅比较两个声明 hash，并在声明 local_path 时检查存在；没有复算文件字节、核对引文内容或实际定位器。`is_official_source` 的比例也来自材料声明。其 `_verify_http:234` 会联网，`run` 会写回文件，本轮均未调用。

当前 `app/runners/wma.py:335` 返回响应 text，`:426` 用 write_text 保存回收材料，可破坏二进制。这是源码发现的明确风险；72 个 hash 不符的直接事实只是“现存字节不等于声明摘要”，本轮没有把每一处不符都归因于同一原因，也没有从现存文件恢复真实原件。

复用顺序：保留历史库原状；从这些失败类别制作净化合成回归样本；需要业务复用时另建有界任务重取获准原件、复算字节、统一实体/证据绑定，再进入现有候选和真人逐字段核验。不能批量把旧 COMPLETE/OK 晋升成 VerifiedFactSet。

## 实际模型标识：未知

17 条 WMA 的数据库 model 均是 `custom:agnes-2.5-flash`，这是配置记录，不是服务端返回的模型身份证据。
本轮逐条检查 WMA 事件：1309 条 session_info_update 全部 detail/raw 为空；13 条 usage_update 也全部没有 payload，另有 4 条运行没有 usage 事件。没有可读取的返回模型标识。

当前 PoC 源码 `app/runners/wma.py:270/287` 使用 `sessions.default()`，`:806–816` 的 PromptOptions 只传回调、时限和取消；没有传入 cfg.model。因此只能说“现存代码使用默认会话，历史实际模型未知”，不能猜默认模型，也不能用这些旧产物证明今天已发布 Agent 的模型配置可用。当前源码不是每次历史运行的完整版本证明。

数据库 mode 中有 23 条 blind、1 条 interactive，只是配置标签；本审计不证明盲测隔离、真人验收、语义准确率或商业价值。

## 可复算与只读证据

配套 JSON：`2026-09-07-poc-history-audit.json`。包含每个 run 的三件套字节 hash、每个 `evidence.artifacts[index]` 的声明/复算摘要和状态、聚合统计、Schema 指纹、旧回执摘要和模型事件计数。

复算口径：只读查询 `SELECT id, case_id, status, mode, runner_kind, model FROM runs ORDER BY id`。对每个 run，仅采用 evidence.artifacts[i].local_path：绝对路径解析后必须在本 run 内；`runs/<同一run_id>/...` 以 PoC 为根，其余相对路径以本 run 为根；解析链接后再次检查边界。禁止 remote_path、跨 run 替代、文件名搜索或网络回补。对定位文件执行 `sha256(path.read_bytes())`，与有效 64 位十六进制声明比较；缺 hash、非法 hash、不能定位分别统计。按 JSON 的 artifact_counts 求和即可复算总表；按 artifact index 回读源文件可独立复算字节。

本轮读取的 175 个 run 内文件在结束时逐一复算，字节未变；SQLite 前后 SHA-256 均为 `7846409cf2076a3621f93325f274430363deca7fa077295c77a1836158091f92`。PoC 代码仅静态读取，未修改。

另以独立只读脚本重新查询全部 run、重新定位文件并复算材料 hash，逐 run 及总体计数均与 JSON 一致；导出 JSON 未包含 URL 或电子邮箱。本报告描述 2026-09-07 的本地历史快照，不说明当前官方链接可达、材料仍有效、云配置可用或新提示词已改善质量。
