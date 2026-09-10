# 裁决包冻结存储边界

本批解决 Python 与 PostgreSQL JSONB 数字表示差异，不改旧摘要或全局 p9b_canonical_json。选择保留已有 Python 确定性 JSON 文本和 UTF-8 SHA256，JSONB 从文本生成，仅用于查询和关联约束，禁止从 JSONB 重建冻结内容或重新生成历史摘要。将全部数字改成字符串会破坏原契约；为数据库改写 Python 摘要会破坏历史锚，因此均不采用。

新增 `adjudication-frozen-json/1.0.0` 封装包含 payload_text、payload_sha256。冻结对象是已有 AdjudicationPackage；冻结前及读取时都验证领域契约，但不使用 model_dump 重写已有记录时间拼写。序列化沿用 digest 的 sort_keys、ensure_ascii=False、紧凑分隔符和 allow_nan=False。拒绝重复对象键、非有限数值、非规范文本、额外封装字段、未知版本及摘要不匹配。恢复时另传可信完整包摘要；包内自洽不是认证、来源当前性或独立人工审核证明。

PostgreSQL 采用文本保存，摘要约束直接针对 convert_to(payload_text,'UTF8')；projection 为 GENERATED ALWAYS AS (payload_text::jsonb) STORED。因此投影与文本只有一个写入来源。JSONB 对 1 与 1.0 或负零的数值等价不构成摘要依据。数据库仍可能无法表示某些 JSON 字符或超范围数字，必须拒绝整个事务，不能替换字符、截断或悄悄降级；新适配器须在事务中持久化后完成读取核验才返回成功。

本批实现封装与解封，并在事务临时表中证明文本保存、生成投影、摘要检查的 PostgreSQL 往返；未创建正式业务表。临时表本身不是业务权限、不可变提案或审核链保证。下批正式迁移需增加存储版本限制、不可变触发器、task/plan/账号外键与关系校验、幂等唯一性和追加审核前驱约束；服务重建来源、重新绑定官方 block，并再次授权及重查当前输入。

验证：整数、1.0、指数、负零、大整数、Unicode 组合字符与空白、旧时间拼写、完整现有来源、篡改及自审反例；真实 PostgreSQL 临时表往返及禁止独立改投影/不匹配摘要。仅此新模块与相关契约测试，不重跑前端构建。设计已确定后，正式业务表和接口接入可按该边界继续，不需要重新开启数字规范化设计。
