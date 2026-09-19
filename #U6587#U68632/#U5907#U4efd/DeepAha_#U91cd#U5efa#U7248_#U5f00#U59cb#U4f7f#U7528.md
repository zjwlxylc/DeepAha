# DeepAha 机会星图 · 3.0.0-rc1

**本包是带真实后端、数据库和用户操作的重建候选版，不是 HTML 原型。** 默认只在本机运行，空库启动不造数据、不代签审核、不调用 WMA。真实 WMA、PostgreSQL、Windows 实机与公网部署仍需要在相应环境验证；不要据本包直接覆盖现有线上项目。

## 先启动
推荐 Python 3.13。解压到一个新目录，Windows 双击根目录 **`启动机会星图.cmd`**。首次会安装依赖，并让你输入首个账号和密码（至少12字符）；没有默认管理员密码。浏览器打开 `http://127.0.0.1:8000`。启动窗口保持打开；使用根目录停止脚本或 Ctrl+C 结束本启动器创建的进程。

Linux/macOS：
```bash
python3 scripts/launch_product.py --install
```
Python 和依赖需要自行安装/联网取得；本包不含 Python、WMA SDK 或离线轮子。数据默认位于用户主目录 `deepaha-data`，不写入原项目数据库。首个账号同时有用户、审核、维护权限；其他账号可分别授权。

## 先体验实际闭环
`examples/` 内三个 ZIP 是**虚构功能样本**，不是实际官方机会。登录工作台，在来源页登记 `https://institute.example.org/`，随后使用收件箱的结果导入入口上传一个样本；阅读内容与备注，点击一次“通过并收录”，在用户端查看结果、收藏并记录行动。空库不会自动通过这些样本。

正式使用时，登记实际允许的来源，导入已回收的 WMA 三文件包，或安装可选 SDK、配置已发布 Agent 后建立真实调查。**WMA 配置缺失不影响已经保存结果的审核。**

## 当前运行架构
```text
外部 Scout 研究文件 → 人工导入来源与调查建议
                                  ↓
已有 WMA 返回包 ← Direct WMA Worker ← 明确的来源/调查任务
          ↓
不可覆盖原件 → 内容投影/局部备注 → 一次整体决定 → 可读总览
                                                        ↓
                               个人偏好 → 关注排序 → 收藏/行动 → 反馈/站内消息
```
数据库承担业务状态，浏览器不持有业务真相。主链不再调用旧方法认证、逐字段事实审核、规则批准或旧 Provider 调查。整体收录不会产生个人肯定/否定资格。

## 主要目录
| 目录 | 当前作用 |
|---|---|
| `backend/src/deepaha/product/` | 当前账号、来源、WMA任务、收录、总览、个人服务、管理和命令行 |
| `backend/src/deepaha/main.py` | 唯一默认 API 装配入口 |
| `web/public/product/` | 第二版视觉基础上的真实产品前端，无演示业务状态 |
| `web/server.mjs` | 可选 Node 同源代理，不启动旧 Next 页面 |
| `scripts/`、`infra/product/` | 本地启动、停止和生产部署配置模板 |
| `backend/tests/product/`、`tests/e2e/` | 新流程自动测试与浏览器验收脚本 |
| `docs/rebuild/` | 执行提示词、设计、实现、使用、部署、迁移、安全与验收 |
| `references/` | 输入规划、旧装配文件、旧配置，只用于比对 |
| `evidence/` | 实际测试输出、截图、输入基线与交付状态 |

其余原模块是保留的共享底座、历史读取或研发代码，**存在源文件不等于被当前应用启用**。不要运行旧启动器、旧测试清库脚本或旧 Provider 工作进程。

## 文档入口
1. [执行提示词](docs/rebuild/00_EXECUTION_PROMPT.md)
2. [产品与技术设计](docs/rebuild/01_DESIGN.md) / [实施记录](docs/rebuild/02_IMPLEMENTATION_PLAN.md)
3. [复用与退役清单](docs/rebuild/03_REUSE_RETIREMENT.md)
4. [接口与输入契约](docs/rebuild/04_API_AND_CONTRACT.md)
5. [使用手册](docs/rebuild/05_USER_MANUAL.md)
6. [部署与启动](docs/rebuild/06_DEPLOYMENT.md)
7. [数据迁移、备份与回退](docs/rebuild/07_MIGRATION_RECOVERY.md)
8. [权限与安全](docs/rebuild/08_SECURITY.md)
9. [验收记录与未验证范围](docs/rebuild/09_VALIDATION.md)
10. [完成边界与后续接续](docs/rebuild/10_COMPLETION_BOUNDARY.md)

## 代码基线
本包从资料库 `DeepAha-main.zip` 的 `d0918ec1245264e271f42a18d54c0fb903000c00` 隔离副本开发。连接器另观察到远程 main 为 `8f0c4a5d252d785444695930610ada4f8b8a0cb0`，但没有把该远程树完整下载合并。本包不包含你本机未上传的更改，也没有对远程仓库进行提交、推送或部署。

## 重要能力边界
当前提供**偏好与关键词相关性排序**，不是已经训练、验证的 AI 匹配模型；所有新收录内容的完整资格判断仍为“暂不能完整判断”。现有资格引擎源码保留，但未把新总览强行送入旧规则链。通知仅实现站内记录与可确定日期的日历导出，**没有微信/短信/邮件送达或支付结算**。这些不是被模拟按钮替代的已完成能力。
