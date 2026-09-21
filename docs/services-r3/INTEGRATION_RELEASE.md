# Mobile R3 集成与发布

本次将用户验收的 Mobile R3 完整源码迁入 D:\DeepAha，基于 main edb01d247ec5069624b24682c89ac5660a68db6f 进行三方整合。源目录位于 D:\DeepAha_Mobile_R3_订阅荐源与微信分享_完整源码_20260921\DeepAha_Mobile_R3；原包3481文件全部哈希通过。保留 main 已有 PostgreSQL json 导入修复、部署工具、pypdf 6.19.0 和 LF/原始契约字节规则；未覆盖本地运行环境或数据。

产品全量329通过、2项原有PG opt-in本地跳过；真实PG共8项另在专用临时库通过。会员112项通过；原R2及新增R3/分享页面在本机原生Chrome通过。验证细目在 evidence/services-r3/integration；完整外部日志及发布回执在 D:\DeepAha-r3-release。

集成只调整测试工具的严格CSP等待、异步登录等待，以及Windows压缩包非法路径样本/原始路径校验；保留验收业务和前端指纹 mobile-r3-7f6388bb22f0。新增专用PG事务回归及ops/mobile_r3/release.py。

正式环境仍命名staging/8100，staging域名使用独立staging-isolated/8200。部署使用独立不可变release及mobile-r3-v1运行环境；先备份、添加14张mbr表、逐行核对旧数据、空库恢复及对象校验，再切换。升级后若失败，API与Worker均保持停止，不自动启动旧版本。隔离staging验收后恢复inactive/disabled按需模式。

首次上线套餐仍为草稿；服务周期检查、外部调查关闭。站点分享主域名按实际正式入口配置为https://www.deepaha.com。宿主未配置微信AppID/AppSecret：公开分享落地、OG、封面可验证，微信JS-SDK定制卡片及手机微信实测不在本次通过范围；无自动支付/真实付费WMA调用。

本次实机回执保存在服务器 /var/backups/deepaha/mobile-r3/<build>/<environment>/receipt.json，并下载到 D:\DeepAha-r3-release。原包关于未部署的历史报告保持原样；最终以这些执行回执为准。
