# DeepAha 3.2.0-rc1 · SG2

- 在 SG1 可行动粒度基础上实现多类型 Opportunity Core。
- 竞赛、科研、奖学金、人才政策/补贴、升学/夏令营、成长实践不再强行套用岗位语义。
- 新增 category-specific presentation contract，模板只改变呈现，不改事实。
- 新增 `program_tiers / region_variants / action_units` producer 兼容层；旧 WMA 包继续可读。
- 嵌套 actionable unit 只发布最具体行动前沿，避免重复卡。
- 非招聘 GROUP 默认只做 scope；无线上申请链接不阻止展示。
- 保留陌生字段、Evidence 和原文，可全文搜索。
- 增加 6 个虚构多类型体验包和 SG2 浏览器验收脚本。
- 真实 SG1 招聘数据回归仍为 58 GROUP + 106 POSITION → 106 Catalog Target。
- 不进入 Eligibility、AI ranking、SG3 生命周期或商业化。
