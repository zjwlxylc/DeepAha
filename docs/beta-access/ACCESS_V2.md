# 账号权限与邀请码调整（2026-09-20）

当前状态：**DEPLOYED_AND_VERIFIED**。已发布到现有隔离 staging，www 未发布。

- 密码4–256字符，注册、改密、重置与宿主CLI一致。
- 新邀请码4位数字，保留前导0；旧长码按原有效期继续使用。
- 仅普通用户、审核员、维护员三种角色。维护员继承全部审核权限，并管理采集、邀请码与账号。
- 历史admin角色显式迁为operator；账号和密码保持，旧会话及重置码失效。
- 管理弹窗采用紧凑权限卡片，复选框19px，文案与按钮不再挤压换行。

验证：31个product测试文件独立RC=0（含17项准入测试、两套独立Gold Oracle、迁移及部署静态契约）；compileall和三项前端检查通过。Chrome验证四字符注册、四位发码、维护员账号管理、角色保存及桌面/窄屏弹窗，JavaScript错误0。窄屏只验证弹窗布局，原有工作台仍要求桌面使用。

证据：evidence/beta_access/v2/。仅允许部署staging-isolated；不发布www，不推进Ops Gateway，不推送GitHub main。

## 本次部署
- 源码：`d32082adfd17d535c415f85ea79c88057e0c2488`，本地分支 `feat/beta-invitations-users`。
- 发布：`/opt/deepaha/staging-isolated-releases/beta-access-20260920-d32082ad`。
- 备份：`/var/backups/deepaha/staging-isolated/beta-access-20260920-d32082ad`。内含数据库、原件、环境文件及角色回退快照；pg_restore至独立空库实证通过。
- 2,263个包内文件SHA256一致；宿主注入的2个WMA秘密比对值精确命中0。
- 1个历史admin账号迁为operator，所有已有密码散列保持一致，既有维护员保留。
- 实机验证维护员审核入口及账号管理、审核员禁止账号管理、4位邀请码并发单名额、4字符注册/重置、角色变更会话失效。所有合成验收账号已停用、邀请码已撤销。
- API/Worker均active，NRestarts=0；www仍指向`/opt/deepaha/releases/3.8.0-rc1`且注册开关未变。原有外层Basic Auth保留，TLS访问预期401，应用验收经宿主8200执行。

使用入口：[用户管理](https://staging.deepaha.com/manage/users)、[邀请码](https://staging.deepaha.com/manage/invitations)。原账号名和密码继续使用，迁移涉及的账号需重新登录。浏览器已登录旧页面时请刷新。

最终回执：[staging_receipt.json](../../evidence/beta_access/v2/staging_receipt.json)。仅源码提交后补充交付记录；未向GitHub推送。
