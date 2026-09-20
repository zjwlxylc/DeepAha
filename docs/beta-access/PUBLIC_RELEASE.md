# Public Beta 邀请准入发布

用户于2026-09-20确认隔离staging验收通过，授权合并main、推送、打标签并发布正式站。

已发布标签：`v3.8.0-rc1-beta-access`。说明：新增邀请码注册与用户管理；密码最少4字符，邀请码4位数字；维护员继承审核员全部权限并统一管理账号；优化权限设置弹窗。

发布以 `ops/beta_access/deploy_public.py` 为入口，沿用正式站现有 `staging-current`、API/Worker staging服务及8100端口。隔离staging保留。先核对旧指针、确认无待处理调查，停服备份并在空库恢复演练，仅补建三张准入表，迁移历史admin角色，保留已有密码及维护员。只将注册开关设为邀请注册，不改WMA密钥或调用WMA，不改Nginx/Ops Gateway。

切换后进行真实HTTPS登录、维护员审核与管理权限、4位邀请注册、4字符密码及普通用户权限验证；合成验收账号停用，邀请码撤销。故障恢复原指针及环境配置；角色迁移有并发保护的补偿回退。新增表可保留，禁止将备份覆盖恢复到当前数据库。

应用代码与已人工验收的 `d32082ad` 一致；本次仅增加正式站发布编排与交接文档。此前31文件全产品回归证据保留，本次复核账号与部署定向回归。

## 发布结果

状态：**DEPLOYED_AND_VERIFIED**。
- 正式入口：https://www.deepaha.com；https://deepaha.com 保留路径与查询参数301跳转。
- 标签：`v3.8.0-rc1-beta-access`，源码提交 `b35ccd030d4e003aed2af77c86b8e1e96700b013`。
- 发布目录：`/opt/deepaha/releases/beta-access-20260920-b35ccd03`；指针 `/opt/deepaha/staging-current`。
- 旧版本：`/opt/deepaha/releases/3.8.0-rc1`。
- 备份：`/var/backups/deepaha/public-beta/beta-access-20260920-b35ccd03`，包含database.dump、objects.tar.gz、staging.env、角色回退映射及SHA256SUMS。pg_restore独立空库演练通过。
- 原有表行数及密码散列保持一致；正式维护员保留，未复制staging账号或数据。仅新增准入表并开启邀请注册。
- 2,267个发布文件SHA256一致；宿主WMA Key/Agent ID两个精确比对值0命中。
- HTTPS登录、维护员审核与管理权限、四位邀请/四字符注册、普通用户隔离、apex重定向通过；合成账号已停用，邀请码撤销。
- API与Worker均active，NRestarts=0；隔离staging仍为d32082ad，Basic Auth不变。
- 原有WMA宿主配置保留，本次未触发真实WMA调用。无Ops Gateway或Nginx变更。

最终回执：[public_receipt.json](../../evidence/beta_access/public_receipt.json)。主线后续仅补交付记录，部署代码由上述标签精确定位。
