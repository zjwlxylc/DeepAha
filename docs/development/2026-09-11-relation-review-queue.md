# 桌面关系提案审核队列

原列表只提供编号和创建时间，查找待审或失效记录需要逐个打开详情。本批在相同 relations 地址接入当前审核队列：显示关系类型、提案理由、所选条件 ID、当前状态和自己创建的标记；支持当前页状态筛选、重新读取、下一页及返回第一页。每次打开详情仍重新核对。原导航索引 API 保持不变。

新增私有 GET unit-plans/{plan}/relation-queue。读取在同一事务内持有任务锁，与已有写入串行；统一重建当前 CrossLevelReview，逐份使用已有完整历史回放和冻结包验证，再做来源/权限重查。按 proposal_id 升序查询，每页最多 50 份，仅返回轻量导航字段，不返回原件或冻结包。next_after 是导航游标，不是来源版本或批准凭证。页间不承诺一致快照，界面只展示当前页及本次读取时间，不累加过期状态或宣称全局待办数。

状态不授予审核权限：自己创建的提案提示由他人独立审核，最终自审限制仍由原写入服务执行。失败隐藏旧卡片，重试保留当前页游标；路由按任务/岗位重新挂载。固定 executable=false、overall_qualification=UNCERTAIN。不新增跨提案冲突裁决、覆盖完成判定或资格编译语义。

## 实际验证

- 实际 PG/API 合成样本：空队列、两份提案、独立批准、当前状态、原创建者标记、另一审核者视角、游标后读取、错误任务/岗位以及范围变化后全部 STALE。见 evidence/2026-09-11-relation-queue-api.xml；导出 web/tests/relation-queue-fixture.json。
- 新路由关闭入口、无关角色、未登录共 3 项通过；见 evidence/2026-09-11-relation-queue-gates.xml。
- 9 项前端 action/组件测试通过：实际导出回执、错误归属/状态/执行标记/游标/重复记录/身份标记、筛选与失败后的同页重读；见 evidence/2026-09-11-relation-queue-unit.xml。
- 新增队列桌面 Playwright 场景通过（7.0 秒），覆盖筛选、刷新、STALE 和撤权显示；原新建保存刷新、详情追加审核两项同批通过。首次新场景失败由选择器同时匹配 option 和卡片文本导致，限定 article 后通过。未修改产品逻辑以迎合测试。
- 截图 evidence/2026-09-11-relation-queue.png 已由图像工具检查，无横向溢出。浏览器使用真实 PG 导出的合成响应，不构成真人验收。
- TypeScript、定向 ESLint、Ruff 和 mypy 通过。没有重复整站本地测试/生产构建，没有调用 WMA 或改动 Evidence Gate。

前序 PR #46 的候选 70bd417e7584ee9697719612b223ecab406c6390 经 CI run 34503801545 九项成功后合并为 2ceef1ac71ff75ec5384cae3cd300a16786caf0b，代码树均为 3960f0431d4c1c604b0ba1420772082c54429fde。本批基于该 main 开始。
