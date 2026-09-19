# 实际验证与完成边界

版本：3.0.0-rc2。状态：文件/接口对齐开发完成；生产环境适配与真实WMA验证未完成。

## 1. 已执行证据

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 当前产品定向及回归 | 78项通过（含29项新增来源对齐用例） | `evidence/source-import/19_verified_product.txt` |
| 原导入工具相关测试 | 44项通过 | `evidence/source-import/13_importer_regression.txt` |
| 网页模块语法/无演示业务状态 | 通过 | `evidence/source-import/16_final_frontend.txt` |
| 时间/HTML转义 | 缺失、非法、有效时间及文本转义检查通过 | `web/scripts/test-product-core.mjs` |
| 实际WB研究文件 | 18批次、52来源候选、72观察、74Brief、212研究依据记录 | `evidence/source-import/05_actual_WB_format.json` |
| WB→原工具导出→主系统→原工具反馈 | 隔离SQLite接收48候选，4未选；重启回执一致，反馈bundle匹配 | `evidence/source-import/12_actual_archive_roundtrip.json` |
| 实际页面与HTTP操作 | 9项交互检查；真实API，没有模拟业务响应；页面脚本错误0 | `evidence/source-import/11_browser_checks.json` |
| rc1数据升级 | 测试先构造仅rc1表边界，再备份、加表、验证原账号不变和重复升级 | `test_additive_upgrade_keeps_accounts_and_original_rows` |

最后一轮全产品测试退出码0。保留了RED、修复中间结果及一次执行超时输出；这些文件不算最终通过证据。上轮rc1的evidence文件仍保留作历史，不能把其测试数重复累计成新增验收。

## 2. 真实研究原件回放的准确含义

输入 `WB-scout.zip` SHA-256：`087dae925b1919f8db731b65afa7de81644aaa34fc72b7fb1513033206244191`，大小17,032,873字节。

实际原件在临时目录中由v0.3.1工具读取并重新导出，主系统从原件重建得到相同候选；临时库接收48个非阻断候选，4个入口/身份问题候选未选。正式Source=0、Task=0、Opportunity=0；没有调用WMA、没有替用户签来源批准，也没有修改用户真实研究状态。

这证明兼容性、保存、回读和反馈结构，不证明网站今天可用、评分正确、52个来源全部值得采用或研究者真实执行了多少次联网调查。44项工具测试只涉及选定模块，不冒充原工具全部平台功能已经验证。

## 3. 浏览器证据限制

本环境原生Chromium访问本机HTTP报 `ERR_BLOCKED_BY_ADMINISTRATOR`，记录于 `10_native_probe.json`。随后显式采用测试专用HTTP桥接，将页面读写送到真实运行API；在about:blank测试页为UUID生成补了浏览器随机字节实现。桥接与UUID适配都只在测试脚本里，不打进业务前端。

因此9项检查不能证明原生Cookie、CSP、真实下载、导航、生产HTTPS或实体手机已通过。1440桌面、720宽重排和390宽用户总览已检查；720宽只是200%缩放对应的布局近似，不是原生浏览器缩放实测。桌面截图在 `evidence/source-import/screenshots/`。

用户环境可运行 `tests/e2e/source_import_browser.py`（不加--bridge）验证原生链路。脚本要求显式隔离测试授权、loopback地址、测试账号及研究包路径；不要向真人库运行。

## 4. WMA与身份边界

使用可控测试客户端验证：生成的task.json包含已批准候选修订和完整Brief；正常回收生成PRODUCTION_RUN_COMPLETED，仍未批准机会；来源政策变化后不创建远程运行。真实腾讯SDK/凭据未取得，本轮没有实际腾讯调用、付费、网络访问或模型选择变更。

系统反馈从已提交数据库读取。原工具检查结果包含结构PASS、bundle_binding=MATCH，但authenticity=UNVERIFIED且不改正式状态，这是正确的离线信任边界，不应篡改成“签名已验证”。

## 5. 未验证/未纳入

Windows/macOS实机、PostgreSQL、NGINX与Docker实际宿主、真实WMA、Codex/ChatGPT资料库实际连接、长期并发与负载未验证。旧 `/api/scout-import/v1` 单批协议未实现到重建版，当前工具主导出路径已对齐。没有自动执行来源合并/退役提案，没有自动资料库归档，没有新增支付或推荐模型。

全部测试仅使用临时库/隔离服务，未向现有公司服务器部署，未修改远程仓库或用户真实数据库。

## 6. 可复现命令

```bash
PYTHONPATH=backend/src python -m pytest backend/tests/product -o addopts='' -q
node web/scripts/check-product.mjs
node web/scripts/test-product-core.mjs
cd tools/source_asset_importer
PYTHONPATH=. python -m pytest tests/test_research.py tests/test_workspace.py tests/test_patch_workbench.py tests/test_research_library.py -o addopts='' -q
```

真实文件回放命令（自行提供文件，永远在临时库运行）：
```bash
python tests/e2e/source_import_real_archive.py /path/to/WB-scout.zip --output /path/to/replay-result.json
```

接口用例覆盖身份/CSRF、原件重验、伪造Audit、重复压缩/上传、同run冲突、分组、State去重、接收事务回滚、已提交回执、来源显式关联、政策与Brief快照、原工具反馈、加表升级及代理上限对齐。
