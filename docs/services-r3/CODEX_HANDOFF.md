# Codex 接续

任务：核对并部署本次完整 Mobile R3，不重新造一个独立会员演示系统。

先读 `DESIGN.md`、`RUN_AND_UPGRADE.md`、`DEPLOYMENT.md`、`TEST_REPORT.md`、根目录 `CHANGESET_MOBILE_R3.json` 和 `DELIVERY_STATUS.json`。输入基线以本轮R2 ZIP SHA256为准，当前GitHub/main可能已有其他修复，必须三方合并，不整包覆盖部署脚本或用户未提交修改。

保持：原LOGO与3张海报；整体审核而非逐字段审批；公开机会及依据免费；收费不改变资格结论；原会话/CSRF/角色；原Scout研究包导入；原WMA连接和并发政策。维护员继承审核员来自R2，订阅用户不继承任何管理权限。

新增核心：`deepaha_membership` 业务库、`product/membership.py` 宿主适配、`services_upgrade.py` 升级；`sharing*.py`、`wechat_share.py` 分享；`membership-ui.js`、`sharing-ui.js` 原SPA内页面；原消息/隐私/Worker/迁移工具的最小接线。

验证命令（仓库根目录）：

```text
python scripts/services_r3/verify.py --output evidence/services-r3/codex-verification
python scripts/experience/verify_manifest.py
```

浏览器原生可用时：`python scripts/services_r3/browser_check.py --output evidence/services-r3/codex-browser --transport native`。本轮作者测试环境的原生本地导航被管理员策略阻止，只使用明确标注的真实HTTP桥进行DOM/JS检查，不能把桥测试当作现场Cookie/TLS/手机验证。

本包没有真实WMA/支付/微信密钥；不会收款；默认服务目录为草稿、定时服务关闭。先在staging验收角色、价格快照、同事务定制申请+荐源、网站审核、来源接入、跟踪、清理后新任务阻断、统一消息、公开OG/私有noindex、上传裁切和分享落地。之后独立做PG恢复演练和小规模真实WMA/微信客户端验证。

包内 `validation/membership-s1/src` 是历史测试输入，不是运行入口。旧R2/S1证据保留作历史；只以R3最终验证报告和最终ZIP复验回执报告这次的通过/未验证范围。未验收不推送/合并/上线，按用户原来的单任务窗口和受控合并原则执行。
