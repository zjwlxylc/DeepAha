# R3 服务器发布、备份与回退

本轮没有连接你的服务器，没有 push/merge、切换域名或部署正式站。以下是交给本机操作者/Codex的执行步骤。必须以现场真实服务名、账号、目录、环境文件和端口为准，不能照抄旧聊天中的端口。R2上传包不等于当前远端main，先做三方比较。

## 1. 基线与发布身份

上传R2 ZIP SHA256：`929ab1518f53717018864ffc7904600d9d8a4ca3f1bba52a776631e3dbb3f467`。本轮在它的独立副本开发，没有替换为GitHub某个相近版本。基础产品版本沿用 `3.8.0-rc1`，扩展身份为 `mobile-r3-services-20260921`，前端身份是 `asset-release.json` 内的 `mobile-r3-…`。

服务器应使用新发布目录，例如 `/opt/deepaha/releases/mobile-r3-services-20260921`，不能继续把所有扩展写入同名 `3.8.0-rc1` 目录。历史 `ops/sg8a/install-release.sh` 会复用老目录、且不知道此次迁移，所以本包对R3明确阻止使用它；不会假装存在已验收的一键上线。

## 2. 先预演，再停服务升级

先在隔离staging复制数据备份，验证恢复、依赖安装、权限、原件和新页面。安装 `backend/requirements-postgres.txt`，它包含完整产品依赖与PostgreSQL驱动。使用Python3.13/3.14；设置 `PYTHONPATH` 指向新代码的 `backend/src`。

真实发布前暂停API和worker，并确认远端正在执行的WMA任务状态；不要只杀本地进程就当作远端停止。备份数据库、`objects` 原件目录和宿主的独立配置。密钥不写进源码/ZIP，不复制到测试证据。

在已加载真实宿主环境变量的终端执行：

```bash
python -m deepaha.product.cli upgrade-services --backup /安全的备份目录/before-r3.pgbackup
python -m deepaha.product.cli deploy-check
python scripts/services_r3/build_assets.py --check
```

`upgrade-services` 在新表写入前执行 `pg_dump`、`pg_restore --list`、原件归档以及SHA256清单；备份路径存在时拒绝覆盖。只有`pg_restore --list`不等于完成恢复演练。真实PostgreSQL迁移与完整恢复需要在staging验证。本轮执行过同构SQLite迁移和数据指纹测试，没有本地PG服务，所以不冒充真实PG通过。

本版本给R2新增14张会员业务表，原产品表结构不改。站点分享设置与服务运行配置写入原 `product_meta` 的独立键；不会修改原机会事实、画像/资格/价值规则。原SQLite备份迁移工具已扩展为同时复制、核对会员14表和原表；未升级的旧R2备份须先在隔离副本执行R3升级后重新备份。

## 3. 切换前后检查

选择新的发布指针后启动API，再检查 `/health/live`、`/health/ready`、`/api/site`、首页及原总览。前端身份必须与交付清单一致。再核对登录、原消息、原数据导出、订阅入口、公开分享页和角色权限。

服务运行、外部调查与WMA连接分别是不同开关。先保持关闭完成用户验收，再启动worker并明确启用所需服务检查。不要让一轮测试顺带启用真实收费调用。

NGINX需要将 `/share`、`/share/opportunity/...`、`/share-assets/...`、`/api/share/...`、已配置的 `MP_verify_....txt` 转发到同一个API，不应用Basic Auth保护公开分享页。管理/API凭据仍保持原来的保护。分享图片上传最大5MB；代理请求上限至少给此路径6MB，但不要无边界提高所有上传限制。旧代理若对 `.txt`/图片做单独静态规则，要确认这些分享路径不会被截走。

## 4. 微信配置

先在管理页填写真正使用的HTTPS主域名（例如 `https://deepaha.com`），并让其他域名规范跳转到它。标题、描述、横版封面和方形缩略图均在后台管理。

宿主环境文件单独配置：

```text
DEEPAHA_WECHAT_APP_ID=你的公众号AppID
DEEPAHA_WECHAT_APP_SECRET=你的公众号AppSecret
```

在微信开发者后台按该账号实际权限完成JS接口安全域名、接口IP白名单等配置；如需验证文件，在网站分享页填写微信提供的限定文件名和正文。程序只允许 `MP_verify_` 开头的限定文件名，不提供任意文件写入。

票据缓存位于 `DEEPAHA_DATA_DIR/private/wechat/`，服务器目录权限0700、缓存文件0600；不在公开原件目录内，不进入本包的原件备份。AppSecret不传浏览器；签名接口只服务同源公开分享页，URL去掉片段但保留签名所需查询部分。外部请求只访问固定微信API，失败会脱敏且短暂冷却。

公开OG与微信专用分享是两个层次：OG描述网页；JS-SDK在真实微信里设置分享菜单内容。部署后，真实手机打开 `/share` 与某条 `/share/opportunity/机会ID`，分别发送朋友/朋友圈并核对封面、标题、描述、点击落地。配置回调成功不是用户已经分享成功；程序文案不会混淆。没有可用公众号或权限时，只能确认通用元信息和链接访问，不能保证微信粘贴链接一定显示指定卡片。

参考：Open Graph https://ogp.me/；微信官方JS-SDK文档入口 https://developers.weixin.qq.com/doc/offiaccount/OA_Web_Apps/JS-SDK.html 。本轮OG规范可读取，微信官方页面在研究工具中无法展开；微信接口实现用模拟响应和签名测试验证，目标账号/客户端能力仍需上述实测。

## 5. 回退与恢复

R3代际为 `…-experience1-services1`，不同于R2。历史回退脚本会比较代际并拒绝自动切回旧代码。原因不仅是新表：旧Worker不认识会员任务的执行前权限检查，不能让它处理R3队列。不要删14张表“回退”，也不要只恢复代码后继续跑旧worker。

回退前再次备份R3新增数据。使用升级前备份恢复到全新隔离数据库/原件目录，再匹配旧代码启动；R3之后新增订单/权益/提交要人工对账和处理，不会自动迁回旧系统。本包SQLite恢复和PG恢复脚本都会撤销登录会话、清理heartbeat，并暂停R3服务运行和外部调查开关，待维护员复核后重启。

不要在schema变化后自动启动旧版本；即便新服务启动失败，也应保持停止并检查，而不是冒险让旧Worker继续执行。
