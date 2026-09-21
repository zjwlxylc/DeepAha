"""Build delivery notes from real test receipts, not assumed pass counts."""
from pathlib import Path
import json,hashlib,base64,html,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2];DOC=ROOT/'docs/services-r3';E=ROOT/'evidence/services-r3'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
verification=read(E/'final-verification/verification.json');per=read(E/'per-file-final/per-file.json')
r2=read(E/'r2-browser-final/browser-r2.json');r3=read(E/'release-browser/browser-r3.json');share=read(E/'share-browser-final/share-browser.json');http=read(E/'final-verification/http/http-smoke.json')
assert verification['status']=='PASS' and all(x['returncode']==0 for x in per)
for v in [r2,r3,share]:assert all(x['passed'] for x in v['checks'])
assert http['status']=='PASS'
build=read(ROOT/'web/public/product/asset-release.json')['build']
counts=verification['counts'];mc=verification['membership_counts'];checks=sum(len(x['checks']) for x in [r2,r3,share]);http_count=len(http['checks'])
report=f'''# Mobile R3 开发与验证报告

日期：2026-09-21。状态：完整源码工程候选，待用户/独立审查及目标环境验收。未push/merge/部署。

## 基线
本轮实际上传的R2完整ZIP，106,657,240字节，SHA256 `929ab1518f53717018864ffc7904600d9d8a4ca3f1bba52a776631e3dbb3f467`。先独立解压运行原产品测试：288项，286通过、2跳过。未用另一GitHub版本替代。基础产品版本保留3.8.0-rc1，本轮扩展 mobile-r3-services-20260921，最终前端 `{build}`。

## 已完成
R2原应用内接入订阅服务、套餐/价格/项目管理、版本化订单与有效期、同事务定制申请和荐源、网站线索审核与原来源/任务适配、持续跟踪、原消息/未读和个人导出清理、服务Worker周期检查、OG公开元信息、两种品牌封面及安全上传、微信签名/缓存和可点击落地页。普通用户与工作台共用原会话和导航，不是iframe或第二个登录系统。

升级、源包、恢复也已接线：显式backup-first upgrade-services；原SQLite→目标数据库复制纳入14张会员表；复制后逐表行数和内容指纹核对；恢复后暂停服务运行开关。旧自动服务器安装器对R3阻断，避免复用错误目录或schema失败后启动旧worker。部署需使用本轮手册，不能声称已服务器一键验收。

## 实际验证记录
| 验证 | 结果 | 当前证据 |
|---|---|---|
| 当前完整product测试集 | {counts['passed']}通过、{counts['skipped']}跳过、{counts['failures']}失败、{counts['errors']}错误，共{counts['tests']}项 | evidence/services-r3/final-verification/product.xml |
| S1复用业务/边界/历史装配测试 | {mc['passed']}通过、{mc['skipped']}跳过 | evidence/services-r3/final-verification/membership.xml |
| 每个product测试文件独立解释器 | {len(per)}个文件均退出0，含明确跳过的PG专项 | evidence/services-r3/per-file-final/per-file.json |
| 构建、编译、前端与HTTP阶段 | {len(verification['stages'])}个阶段退出0 | evidence/services-r3/final-verification/verification.json |
| 真实回环TCP/HTTP | {http_count}项通过 | evidence/services-r3/final-verification/http/http-smoke.json |
| 原R2页面与操作回归 | {len(r2['checks'])}项通过，84页面×宽度组合 | evidence/services-r3/r2-browser-final/browser-r2.json |
| 新订阅、荐源、管理、分享设置 | {len(r3['checks'])}项通过，{len(r3['views'])}项布局尺寸记录 | evidence/services-r3/release-browser/browser-r3.json |
| 公开分享落地DOM/JS | {len(share['checks'])}项通过 | evidence/services-r3/share-browser-final/share-browser.json |
| LOGO/三海报及关键业务保护 | 16个文件与上传R2字节相同 | evidence/services-r3/protected-files.json |

浏览器合计{checks}项检查通过，无页面JavaScript错误。以上是具体场景验证，不是所有设备、所有可访问性标准、渗透或业务准确率认证。当前测试基于已有Linux/Python3.13.5/Node22.16环境；完整版本见environment.json。本轮明确pypdf>=5.9,<7兼容范围，没有将原环境的5.9伪装为6.x；没有执行Windows全新依赖安装。

## 新边界测试实际覆盖
同一个登录cookie/CSRF下角色与数据隔离、免费用户不能创建付费跟踪、不同有效期/名额、金额与条款快照、重复请求、原未读与合并消息、清理时取消队列且不重建私人记录、账号停用/订阅到期在远程创建前阻断、上传任务资料后撤销在prompt前阻断、真实Product+模拟WMA客户端从队列到候选/整体审核/发布通知、同事务定制申请+网站提交的错误回滚、非公开目录仍可登录访问原应用但不泄露OG、撤回内容不能分享旧标题、固定外部签名地址和凭据缓存、签名去片段、错误脱敏、限频和轮换、位图上传/重编码/尺寸/越权。

真实宿主WMA模拟客户端测试调用原worker和原审核发布，不是手工在目标机会表塞一行充当端到端。供应商传输仍为模拟，不计作真实WMA调用。Node分享脚本用模拟SDK验证15项行为，也不计作微信客户端成功。

## 初始失败和修正没有删除
01/02/03/04/06阶段在功能缺失时记录失败；随后实现并复跑。05宿主跟踪发现响应返回时私人记录已清理的竞争窗口，改为返回CANCELLED、不恢复记录；真实队列仍取消。07发现禁公开目录不应连已登录用户的原应用HTML一起挡掉，改为仅分享页拒绝、原应用noindex。08发现旧迁移未纳入会员表，补齐复制及恢复暂停。

一次前端命令从错误cwd执行，保留initial-cwd.log，改为web目录后全部复跑成功。R3构建脚本第一版只打印纯函数结果、未写manifest，修改页脚后ASSET_BUILD_STALE正确阻止启动，导致初始逐文件/浏览器运行失败；已修正构建写入并重新执行47个文件和原页面回归。初始per-file目录是失败历史，不作为通过证据。独立复跑另发现一条历史测试仍精确要求旧-experience1后缀，按新schema代际改为更完整的-experience1-services1，单独复跑通过；原失败和复跑日志均保留，未放松跨代际回退禁止。

## 环境与交付边界
Chromium原生本地导航返回ERR_BLOCKED_BY_ADMINISTRATOR，原失败在browser-native；未修改管理员策略。浏览器采用明确测试桥：实际生产DOM/ES模块和真实本地FastAPI/SQLite通过桥交互。它不证明原生导航、Cookie/TLS、Service Worker、微信内核、实体触控/软键盘。

未执行：真实PostgreSQL数据库/备份恢复、真实WMA供应商、真实微信账号/客户端、微信/支付宝收款、Windows实机、实体Android/iOS、独立第三方安全/无障碍审查。套餐默认草稿、服务运行关闭，未产生真实付费调用。自检不等于独立审查，合并发布需用户验收。

最终ZIP另外重新解压到新目录做CRC、文件清单核对和完整测试。事后复验结果写在外部PACKAGE_RECEIPT，避免自校验包内嵌入关于自己的循环校验；最终以该回执为准。
'''
(DOC/'TEST_REPORT.md').write_text(report,encoding='utf-8')
(DOC/'PROGRESS.md').write_text('''# Mobile R3 执行记录

1. 已核验实际R2 ZIP与已登记SHA相同，独立副本原基线286通过/2跳过。
2. 已接入原会话、权限、数据生命周期、服务调度和WMA执行前授权检查。
3. 已完成套餐与订单、同事务定制荐源、原来源/任务与发布通知闭环。
4. 已完成OG、位图封面管理、微信签名与独立公开落地页。
5. 已完成原SPA导航/工作台/消息整合；保留品牌和海报。
6. 所有最终工作树自动测试与浏览器记录见TEST_REPORT；原失败保留。
7. 最终ZIP重新解压结果由单独PACKAGE_RECEIPT记录，不自称已线上验收。

Ruling：用户要求持续实施，不再重复索要设计确认；不push/merge/部署、不请求真实供应商。
Ruling：不自动收款；人工核对和试用分开。无真实微信凭据不冒充卡片验收。
Ruling：不使用不合适的生成图作为实际界面证明，交付的封面为正式LOGO与可复现品牌版式，界面图为实际浏览器截图。
Ruling：发现迁移/恢复/旧安装脚本接线缺口，一并补齐或明确阻断旧脚本，不能只把新页面装进旧包。
''',encoding='utf-8')
status={'release':'3.8.0-rc1','extension':'mobile-r3-services-20260921','parent_extension':'mobile-r2-20260920',
'parent_zip_sha256':'929ab1518f53717018864ffc7904600d9d8a4ca3f1bba52a776631e3dbb3f467','inherited_upstream_commit':'84353c7e5286e276d24af8e0342d4d3441c30ec5',
'frontend_build':build,'artifact_kind':'FULL_INTEGRATED_SOURCE_ENGINEERING_CANDIDATE','this_iteration_human_acceptance':'PENDING','iteration_added_tables':14,
'core_eligibility_value_rules_changed':False,'overall_review_preserved':True,'production_deployed':False,'remote_repository_writes':False,'live_wma_tested':False,'live_wechat_tested':False,'postgres_live_tested':False,'windows_native_tested':False,'physical_mobile_tested':False,'contains_user_database':False,'contains_credentials':False,'self_review':'AUTHOR_SELF_REVIEW_NOT_INDEPENDENT','verification':{'product':counts,'membership':mc,'per_file_suites':len(per),'command_stages':len(verification['stages']),'http_checks_passed':http_count,'r2_browser_checks':len(r2['checks']),'r3_browser_checks':len(r3['checks']),'share_browser_checks':len(share['checks']),'browser_total':checks,'ui_transport':'Explicit test-only bridge to actual HTTP. NOT native Cookie/TLS.','final_zip_receipt':'Separate post-extraction receipt provided with ZIP'},'defaults':{'plans':'DRAFT','service_runtime_enabled':False,'allow_site_enqueue':False,'wechat_enabled':False,'payment':'TRIAL_OR_MANUAL_CONFIRMATION_ONLY'}}
(ROOT/'DELIVERY_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
(ROOT/'RELEASE_STATUS.json').write_text(json.dumps({'release':'3.8.0-rc1','extension':status['extension'],'status':'ENGINEERING_CANDIDATE_PENDING_HUMAN_ACCEPTANCE_NOT_DEPLOYED','details':'DELIVERY_STATUS.json','test_report':'docs/services-r3/TEST_REPORT.md','historical_parent_status':'docs/services-r3/r2-metadata/RELEASE_STATUS.json'},ensure_ascii=False,indent=2)+'\n')
package={'release':'3.8.0-rc1','extension':status['extension'],'main_entry':'backend/src/deepaha/main.py','read_first':'docs/services-r3/RUN_AND_UPGRADE.md','codex_deploy_task':'docs/services-r3/CODEX_HANDOFF.md','server_deployment':'docs/services-r3/DEPLOYMENT.md','release_status':'DELIVERY_STATUS.json','compatibility':'RELEASE_COMPATIBILITY.json','checksums':'FILE_MANIFEST.sha256','contains_user_database':False,'contains_user_objects':False,'contains_credentials':False,'expected_first_server_action':'NONE: review source delta and staging before any controlled deployment','parent_zip_sha256':status['parent_zip_sha256'],'frontend_build':build}
(ROOT/'PACKAGE_MANIFEST.json').write_text(json.dumps(package,ensure_ascii=False,indent=2)+'\n')

def dataimage(path):
 p=Path(path);mime='image/jpeg' if p.suffix in ('.jpg','.jpeg') else 'image/png';return 'data:'+mime+';base64,'+base64.b64encode(p.read_bytes()).decode()

cards=[('订阅方案 · 手机端',E/'release-browser/services-390.png'),('订阅与报价 · 手机端',E/'release-browser/subscription-390.png'),('网站提交 · 手机端',E/'release-browser/sources-390.png'),('持续跟踪 · 手机端',E/'release-browser/tracking-390.png'),('公开分享落地页',E/'share-browser-final/share-landing-390.png')]
thumbs=''.join(f'<figure><figcaption>{html.escape(label)}</figcaption><a href="{dataimage(p)}" target="_blank"><img src="{dataimage(p)}" loading="lazy" alt="{html.escape(label)}"></a></figure>' for label,p in cards)
page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DeepAha Mobile R3 · 完整系统交付</title><style>
:root{{--blue:#0b44b3;--orange:#f86f09;--ink:#182d4d;--muted:#5e718e}}*{{box-sizing:border-box}}body{{margin:0;background:#f4f7fc;color:var(--ink);font:16px/1.85 system-ui,"Microsoft YaHei",sans-serif}}main{{max-width:1160px;margin:auto;padding:36px 26px 80px}}header{{background:white;border:1px solid #e0e8f3;border-radius:24px;overflow:hidden}}header img{{width:100%;height:auto;display:block}}header div{{padding:30px 38px}}.eyebrow{{font-size:12px;letter-spacing:2px;color:var(--blue);font-weight:750}}h1{{font-size:34px;line-height:1.45;margin:8px 0 15px}}h2{{font-size:25px;margin:0 0 20px}}h3{{font-size:19px;margin:25px 0 10px}}section{{padding:30px 36px;background:white;border:1px solid #e0e8f3;border-radius:20px;margin-top:24px}}p{{margin:12px 0}}.muted{{color:var(--muted)}}.note{{border-left:4px solid var(--orange);background:#fff7ed;padding:15px 20px}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:14px 16px;text-align:left;border-bottom:1px solid #e1e8f2;vertical-align:top}}th{{color:var(--blue);background:#f2f6fd}}code{{background:#eef3fb;padding:2px 5px;border-radius:5px;overflow-wrap:anywhere}}pre{{background:#10264a;color:white;padding:18px 22px;border-radius:12px;overflow:auto;line-height:1.8}}.shots{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}}figure{{margin:0;border:1px solid #e1e8f3;border-radius:14px;overflow:hidden;background:#f6f8fc}}figcaption{{padding:12px 15px;background:white;font-size:14px;font-weight:700}}figure img{{width:100%;height:auto;display:block}}.desktop{{width:100%;border:1px solid #e1e8f3;border-radius:12px}}a{{color:var(--blue)}}.stats{{display:flex;gap:18px;flex-wrap:wrap}}.stat{{flex:1;min-width:160px;background:#f1f6fe;padding:18px;border-radius:13px}}.stat b{{font-size:30px;display:block;color:var(--blue)}}footer{{color:var(--muted);font-size:12px;padding:25px 0}}@media(max-width:700px){{main{{padding:14px 12px 40px}}header div,section{{padding:22px}}h1{{font-size:26px}}h2{{font-size:23px}}.shots{{grid-template-columns:1fr 1fr}}.table-wrap{{overflow:auto}}th,td{{padding:10px;min-width:95px}}.stat{{min-width:120px}}}}
</style><main><header><img src="{dataimage(ROOT/'web/public/product/share/default-wide.jpg')}" alt="机会星图品牌封面"><div><div class="eyebrow">FULL INTEGRATED DELIVERY · 2026 / 09 / 21</div><h1>Mobile R3<br>订阅、荐源、定制跟踪与网站分享</h1><p>以你上传的 Mobile R2 完整源码为基线，将服务能力接入原系统的账号、导航、审核、任务、消息与数据管理，不是另一个演示网站。</p><p class="muted">前端版本：<code>{build}</code> · 交付状态：工程候选，尚未线上部署。</p></div></header>
<section><h2>01 / 这次打开的是同一个机会星图</h2><p>原LOGO、三张首页海报、机会总览、画像、资格与价值判断、收藏行动、整体审核、Scout导入和原WMA路线保留。新增页面从“我的”或工作台进入，沿用原登录、权限、CSRF和手机导航。原消息中心与未读提示显示新增服务进展。</p><div class="note">公开机会与依据不因未订阅被隐藏。订阅购买的是持续检查和定制来源跟踪，不改变资格判断，也不保证录取、报名成功或一定发现新机会。</div></section>
<section><h2>02 / 三档服务，后台可调整</h2><div class="table-wrap"><table><thead><tr><th>项目</th><th>基础订阅</th><th>深度订阅</th><th>定制订阅</th></tr></thead><tbody><tr><td>默认期限</td><td>2个自然月</td><td>12个自然月</td><td>先确认方案和期限</td></tr><tr><td>试运营初始价</td><td>29.90元/期</td><td>129元/期</td><td>单独报价</td></tr><tr><td>主题名额</td><td>3个</td><td>10个</td><td>默认10个，可调整</td></tr><tr><td>已发布机会检查</td><td>目标24小时</td><td>目标6小时</td><td>目标6小时</td></tr><tr><td>指定网站</td><td>不包含</td><td>不包含</td><td>默认3个；先审核，默认24小时调查目标间隔</td></tr></tbody></table></div><p class="muted">价格是可修改的初始配置，不是经过真实付费验证的定价。预置套餐全是草稿，维护员确认上架后才对用户显示；历史订单锁定当时条款。</p><p>后台可管理服务项目、套餐版本、价格、名额、周期、报价、开通、撤销和执行记录。试用与人工核对付款分开；不自动续费。续购/换档从下一服务期接续，不进行自动补差价。</p></section>
<section><h2>03 / 用户给一个网站，进入真实处理流程</h2><p><b>用户提交 → 校验与去重 → 自动进入网站线索审核 → 通过 / 补充 / 拒绝 → 维护员接入并授权来源 → 原WMA队列调查 → 原整体审核 → 发布与提醒。</b></p><p>免费用户也可以荐源。定制申请中直接填写一个公开网站，会与申请在同一事务内保存，无需重复填写；只有描述目标而未填网站时，正常先形成待报价需求。通过线索审核不是批准机会事实，采集返回仍进入原审核收件箱。</p><p>用户可以暂停跟踪；到期、停用或清理后，执行前会再次核对权限。隐私清理纳入原数据管理，必要的订单/权益及核对记录明确保留，清理不等于退款。公开来源和正式事实不随单个用户的清理被删。</p></section>
<section><h2>04 / 域名、封面、标题与描述</h2><p>在工作台“网站分享”设置HTTPS域名、标题、描述和封面。提供1200×630横版与600×600缩略图；自定义图片会裁切重编码、清除EXIF，纳入原件备份。OG写在服务端首次返回的HTML中；个人画像、订单和审核页不泄露私有元信息。</p><p>公开分享地址为 <code>/share</code>，机会分享地址为 <code>/share/opportunity/机会ID</code>。落地页可以复制链接，并点击进入网站或对应机会。微信专用样式由独立公开页按需加载SDK，AppSecret与票据只在服务器。</p><div class="note">OG完成 ≠ 真实微信卡片已验收。公众号权限、JS接口安全域名、IP白名单、实际HTTPS与微信客户端需要现场配置并测试；本轮没有这些凭据，未发送真实微信分享。</div><img class="desktop" src="{dataimage(E/'release-browser/sharing-settings-1440.png')}" alt="真实后台网站分享设置截图"></section>
<section><h2>05 / 打开与启用</h2><p>停止旧版，把本包解压到新文件夹；Windows使用Python3.13或3.14，双击原来的 <code>启动机会星图.cmd</code>。保留现有 <code>deepaha-data</code>，不要删除数据库或重新初始化账号。首次R3升级先备份，再新增14张会员表。</p><p>先用维护员审阅并上架套餐。然后在“订阅与服务 → 运行设置”启用周期服务；需要调查定制网站时，再明确打开外部调查开关并选择现有执行连接。原Worker每小时检查一次到期项目，实际完成时间受队列和供应商影响，查看“最近检查”而不是只看开关。</p><p>服务器不能套用SG8-A旧一键安装脚本。R3需要新发布目录、停止API/Worker、备份、执行 <code>upgrade-services</code>、staging复核后再切换。不同数据库代际禁止直接回退旧Worker。</p><p>详细步骤位于包内 <code>docs/services-r3/RUN_AND_UPGRADE.md</code>、<code>DEPLOYMENT.md</code>、<code>CODEX_HANDOFF.md</code>。微信环境变量为 <code>DEEPAHA_WECHAT_APP_ID</code> 与 <code>DEEPAHA_WECHAT_APP_SECRET</code>；不要把真实值发进前端、源码或截图。</p></section>
<section><h2>06 / 验证范围</h2><div class="stats"><div class="stat"><b>{counts['passed']+mc['passed']}</b>自动测试通过 · 另2项PG跳过</div><div class="stat"><b>{checks}</b>浏览器具体检查通过</div><div class="stat"><b>{http_count}</b>真实本地HTTP检查</div></div><p>当前product共{counts['tests']}项，{counts['passed']}通过、2项需要真实PostgreSQL而跳过；复用会员测试{mc['passed']}通过。{len(per)}个product测试文件独立解释器复跑均退出0，原R2页面也重跑了115项检查。</p><p class="muted">浏览器原生本机导航被管理员策略阻止，使用明确的真实HTTP桥检查实际DOM/JS，不能证明原生Cookie/TLS、微信客户端或实体手机。本轮是真实程序＋隔离合成数据；未请求真实WMA、未接通支付、未部署服务器，也未进行独立第三方审查。最终压缩包CRC、重解压清单和复验结果请看另附校验回执。</p></section>
<section><h2>07 / 实际界面</h2><p class="muted">以下来自本轮浏览器执行，不是AI生成的产品效果图。测试账号和机会均为隔离合成资料；长截图中的底部导航停留在截取时的视口位置。</p><div class="shots">{thumbs}</div></section>
<footer>DeepAha · Go Deep. Find Yours. · 本说明和源码包一起交付。真实生产状态以你的服务器与独立验收为准。</footer></main></html>'''
(DOC/'DELIVERY_GUIDE.html').write_text(page,encoding='utf-8')
Path('/mnt/data/DeepAha_Mobile_R3_运行与交付说明.html').write_text(page,encoding='utf-8')
print('docs complete',build,checks,http_count,len(page))
