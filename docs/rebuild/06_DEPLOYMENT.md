# 启动、配置与部署

## 1. 已验证环境与边界
本轮实际验证 Linux 容器、Python3.13.5、SQLite、FastAPI 与 Chromium 显式测试桥接。Windows启动脚本/DPAPI、Mac、Python3.14、PostgreSQL、Docker与NGINX配置未在对应宿主实机验收。它们是可执行代码/配置交付，不是已经上线声明。

## 2. Windows本地
准备Python3.13，解压到新目录，双击 `启动机会星图.cmd`。首次安装 requirements-product 并交互创建账号。账号和密码不经过聊天，不写入代码。启动地址 `http://127.0.0.1:8000`。完整包不是双击HTML；前后端必须同时由服务运行。

数据默认 `%USERPROFILE%\deepaha-data`。不要把它设为旧的真人库目录。可在PowerShell指定新目录：
```powershell
$env:DEEPAHA_DATA_DIR='D:\DeepAhaData-rebuild'
python scripts/launch_product.py --install
```
日志在数据目录。关闭启动窗口前按Ctrl+C；或双击停止脚本。停止脚本核对PID、创建时间、工作目录和命令，只处理自己创建的进程。8000端口被别的程序占用时明确停止启动，不杀掉别的服务。

## 3. Linux本地及手动命令
```bash
python3.13 -m venv .venv-product
.venv-product/bin/python -m pip install -r backend/requirements-product.txt
export PYTHONPATH="$PWD/backend/src"
export DEEPAHA_DATA_DIR="$HOME/deepaha-data-rebuild"
.venv-product/bin/python -m deepaha.product.cli setup
.venv-product/bin/python -m deepaha.product.cli serve --host 127.0.0.1 --port 8000
```
另一个终端配置相同环境并启动Worker：
```bash
.venv-product/bin/python -m deepaha.product.cli worker
```
也可直接 `python3.13 scripts/launch_product.py --install` 管理两个进程。

## 4. 账号与数据
```bash
python -m deepaha.product.cli user-add alice --roles user
python -m deepaha.product.cli user-add reviewer01 --roles reviewer
python -m deepaha.product.cli user-add maintainer01 --roles operator
python -m deepaha.product.cli user-disable alice
python -m deepaha.product.cli password-reset alice
```
上面python需在当前虚拟环境、PYTHONPATH和同一数据目录下执行。密码交互隐藏输入；自动化可用 `--password-env` 指向宿主短期环境变量，不在命令参数中写明文。

## 5. Direct WMA
安装可选依赖：
```bash
python -m pip install -r backend/requirements-wma.txt
```
沿用已发布的“DeepAha 官方机会调查智能体”；模型、技能和系统提示词由WorkBuddy已发布配置管理，不新增per-run模型覆盖。当前代码复用原归档 `DirectWmaClient` 与发布绑定检查，没有猜测新的腾讯接口。

本地在管理页填写Agent ID、Source App和API Key，可加密保存；安装SDK后显式测试并启用，Worker才会领取任务。Windows使用当前用户DPAPI，Linux使用本地受保护密钥；换电脑/操作系统时重新注入凭据，不复制Windows密文冒充可移植秘密。

生产使用宿主环境注入：DEEPAHA_WMA_AGENT_ID、DEEPAHA_WMA_API_KEY、DEEPAHA_WMA_SOURCE_APP和DEEPAHA_WMA_ENABLED=1。后台不会读回API Key。**本轮未获得凭据、未装SDK、没有真实腾讯调用。**已发布Agent的实际技能、输出格式、预算、会话恢复与文件取回须小规模验证后启用周期检查。

## 6. 生产配置模板（未运行Docker/PG）
保留模块化单体，不拆微服务。`infra/product/Dockerfile` 和 `infra/compose.yaml` 提供API、PostgreSQL和可选Worker，数据库使用持久卷、不发布数据库端口；不再使用旧测试配置的tmpfs数据库或默认密码。

复制 `infra/.env.example` 到 `infra/.env`，在实际宿主填入秘密和数据库URL，例如形态 `postgresql+psycopg://用户名:URL编码后的密码@postgres:5432/数据库`。生产强制Secure Cookie、显式Host/Origin和PostgreSQL。默认关闭公开目录、自助注册和WMA，须经营者明确启用。秘密文件权限限制为仅部署账号可读。
```bash
cd infra
docker compose up -d postgres
docker compose build api
docker compose run --rm api python -m deepaha.product.cli setup
docker compose up -d api
# 实际SDK和凭据验证后，配置 WITH_WMA=1、WMA_ENABLED=1，重建并启动可选Worker。
docker compose --profile wma up -d --build worker
```
此命令不替你创建TLS证书，也不授权公网发布真实材料。配置好现有NGINX，将对应站点转发到127.0.0.1:8000；参考 `infra/product/nginx.conf.example`。不要用示例覆盖当前网站配置。也可采用提供的systemd单元；需先准备系统账号、`/opt/deepaha`、虚拟环境、`/var/lib/deepaha`与受保护的`/etc/deepaha/product.env`。

## 7. 保留3000端口时
`cd web && npm start` 使用Node内置HTTP代理，不安装React/Next依赖，不启动旧页面。API和代理都要运行。额外Host/Origin在宿主环境中明确配置；默认不需要该代理，优先NGINX直接转发8000。

## 8. 发布检查
先在隔离副本做数据库初始化/旧身份映射与备份恢复；验证读者、审核、维护越权；验证会话失效与CSRF；验证WMA离线仍能读旧总览并审核已存内容；验证真实正常/局部缺口/整包不适用三例；验证实际浏览器Cookie、长内容、手机和200%缩放。记录真实模型、Agent发布版本与成本观测，不把测试假件算作线上数据。

Docker镜像标签与PG驱动范围需要在实际部署时冻结到验证过的版本/摘要。当前没有离线轮子、生产镜像构建或持续负载证明。代码提供路径，交付记录不把未执行步骤写成PASS。
