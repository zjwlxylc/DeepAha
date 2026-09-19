# 06｜项目级验收门与停止线

## Gate A：Actionable Granularity

必须同时成立：

- 多岗位公告的总览卡片数等于可行动岗位数；
- GROUP 不冒充机会；
- 单项机会仍只显示一条；
- user action / reminder / feedback 是 target-scoped；
- 真实 WMA 样本通过。

未通过：不进入个性化开发。

## Gate B：Opportunity Core

- 招聘、竞赛、科研、政策、奖学金至少五类；
- 未知字段不丢；
- 子结构不串 scope；
- 类型模板只改变呈现，不改变事实意义。

## Gate C：Currentness

- 更正只影响正确 unit；
- 旧 deadline/reminder 失效；
- “本轮没看到”不自动等于撤回；
- 历史版本可查。

## Gate D：Eligibility Trust

- INELIGIBLE 必须有明确冲突证据；
- 无证据/有例外/作用域不明 → UNCERTAIN；
- Gold pairs 上无 silent false-negative；
- 资格判断不会由 LLM 单独落锤。

## Gate E：Personal Value

- Top-N 排序优于关键词基线；
- 解释能够指出目标、条件、时效和风险；
- 不用伪概率包装不确定性；
- 用户可以关闭个性化。

## Gate F：Action Loop

- 收藏、准备、申请、结果链可持久；
- 更正会触发正确变更提醒；
- 用户反馈不直接改硬规则；
- 反馈可以进入离线评估资产。

## Gate G：Human Value

在真实设计伙伴上至少能回答：

- 用户以前是否知道？
- 是否认为值得关注？
- 是否采取行动？
- 为什么没有行动？
- 是否发生申请/面试/录取/其他结果？

在 Gate G 之前，不能把“推荐准确”写成商业完成。

## Gate H：Production

- PostgreSQL 当前版本迁移通过；
- backup/restore 真演练；
- native browser + Android/Windows；
- RBAC/CSRF/session/secret；
- WMA 故障隔离；
- 负载与 P95 有实测记录；
- 数据权请求可执行。

## Gate I：Commercial

只有 Gate G + H 通过后：

- 支付；
- 订阅；
- 家长赠送；
- 高校采购试点。

## 全局停止线

出现以下任一情况，不得靠扩大范围“解决”：

1. 需要恢复旧逐字段人工批准才能让普通机会进入总览；
2. 需要让 WMA/LLM 成为正式事实批准者；
3. 需要把同一事实复制成几十个独立权威值才能支持岗位卡片；
4. 需要标题相似度自动合并正式身份；
5. 需要真实用户库跑清表/破坏性集成测试；
6. 新子目标明显依赖尚未通过的前一 Gate；
7. 每个站点都开始新增专属生产爬虫逻辑；
8. 为了活跃度加入与 Opportunity 无明确关系的泛资讯；
9. 为了“AI感”把所有候选 pair 发送给大模型；
10. 为了收费把公开官方机会信息锁进付费墙。
