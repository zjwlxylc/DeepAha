> 后续更新：本功能已获用户验收并发布正式站，当前发布与回退信息见 [PUBLIC_RELEASE.md](PUBLIC_RELEASE.md)。以下为隔离staging阶段记录。

# 邀请准入与用户管理：staging 交付记录

> 以下为首版上线历史记录（c6636456）。2026-09-20 追加调整：4字符起密码、4位数字邀请码、维护员合并账号管理且继承全部审核权限，交付已完成，当前发布为 d32082ad，详见 [ACCESS_V2.md](ACCESS_V2.md)。

状态：**DEPLOYED_AND_VERIFIED**。仅隔离 staging 发布，正式体验站 www / deepaha.com 未发布本功能。

## 使用入口
- 登录：<https://staging.deepaha.com/login>
- 发码：<https://staging.deepaha.com/manage/invitations>
- 用户管理：<https://staging.deepaha.com/manage/users>
- 受邀注册：<https://staging.deepaha.com/register>
- 忘记密码：<https://staging.deepaha.com/reset-password>
- 登录后修改密码：`/account/security`。

管理员账号为 `beta_admin`，初始登录资料保存于本机 `D:\DeepAha-beta-access-work\private\staging-admin.json`，目录ACL仅当前用户与SYSTEM可访问；不进入仓库或报告。请首次登录后修改密码。staging原有Nginx Basic Auth仍保留，访问还需要此前的外层认证信息；本次未更改这些信息。

具体发码、角色权限、重置密码及隐私说明见 [OPERATIONS.md](OPERATIONS.md)，设计见 [PLAN.md](PLAN.md)。

## 已部署版本
- 应用源码提交：`c66364565f61354b563ed341479e23a77acd7a33`。
- 发布目录：`/opt/deepaha/staging-isolated-releases/beta-access-20260920-c6636456`。
- current：`/opt/deepaha/staging-isolated-current`。
- 服务：`deepaha-api@staging-isolated`、`deepaha-worker@staging-isolated`，8200，独立数据库和数据目录。
- 保留隔离Worker的 `--isolated-fixture-mode`、WMA关闭配置、空库初始化保护入口；未改Ops Gateway。
- 本地开发分支：`feat/beta-invitations-users`。本轮提交保存在本地，未推送GitHub或修改远程main。

## 验收与证据
- 产品测试31个文件逐文件RC=0；其中新准入与账号测试12项。最后的认证/CLI修改又通过API、operations、worker和SG8-A定向回归。
- compileall、product/SG7.2前端契约、两套独立Gold Oracle、SQLite typed-copy migration harness、SG8-A env/systemd/nginx/compose/script静态契约通过。
- 本地真实HTTP与Chrome关键流程通过，移动端注册及桌面管理已目视检查。
- 2,255个发布文件按包内SHA256核验。真实宿主WMA Key/Agent ID共2个比对值，源码及嵌套ZIP精确命中0。
- 停服备份后，pg_dump在新建空库实际pg_restore成功且账号数量吻合；演练库已删除。原件归档3个文件，并生成数据库/原件备份SHA256SUMS。
- 迁移仅新增表，已有表行数保持不变。真实PostgreSQL单码并发注册、重置码单次使用、会话失效、用户权限和账号停用验证通过。
- API/Worker持续active，最终复核重启计数均0。staging外网TLS正常且返回预期Basic Auth 401；认证后的应用功能通过宿主8200 HTTP验证，外层Basic Auth未绕过或移除。
- Smoke为明确标注的合成测试，注册账号已停用、邀请码已撤销，不代表真实用户体验研究。

回执：`evidence/beta_access/staging_receipt.json`；功能验收：`evidence/beta_access/staging_smoke.json`。

## 回退材料及过程记录
- 当前版本切换前备份：`/var/backups/deepaha/staging-isolated/beta-access-20260920-c6636456`。
- 前一可运行版本：`beta-access-20260920-186ca7e4`。
- 若需完整回到功能上线前：原发布 `e97ad37a0a81c9d189fa727475103ef8ae4f4ed9`，原环境文件保存在首次备份 `.../beta-access-20260920-2333a522/staging-isolated.env`。须同时恢复代码与注册开关，不能只回退代码而让旧版开放无邀请码注册。
- 不回滚/覆盖当前数据库；新增表可留存。灾难恢复需新建空库单独验证。
- 首次候选缺少现有隔离Worker参数，实际检查发现后恢复了原代码和注册配置；保留隔离能力并增加参数预检/持续运行验证后重发成功。没有影响www。

下一步是用户在staging人工体验；向正式体验站发布需另行安排。本记录不代替人工验收，也不自动授予正式发布授权。
