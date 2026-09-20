# 本地运行与既有数据升级

## 运行前

使用 Python 3.13 或 3.14。Node 22 只用于前端检查；当前产品静态界面由 Python 服务提供，不要求再启动一套 Node 前端服务器。程序允许 WMA SDK 缺失时进行浏览、管理、导入已有文件和整体审核；默认启动器的 requirements-product.txt 仍会尝试安装 SDK。PostgreSQL 驱动按宿主需要另装。后台不会凭空产生真实机会。

不要将新包覆盖到仍在运行的旧目录。先停止本机旧启动器管理的 API/Worker，将本包解压到新目录。数据位于 `%USERPROFILE%\deepaha-data`（可用环境变量改为独立目录），不包含在源码包内。

## Windows 新安装

在解压目录打开 PowerShell：

```powershell
py -3.13 scripts/launch_product.py --install
```

也可双击 `启动机会星图.cmd`。首次安装需要联网取得 requirements 中的依赖；首次启动按提示设置自己的维护账号，密码输入不回显。原最低 4 字符兼容规则未改，实际使用请设置足够长的独立密码。源码不预置可登录的正式账号。

访问终端显示的本地地址，默认 `http://127.0.0.1:8000`。`/review/overview` 是审核工作台，`/manage/sources` 是来源，`/manage/tasks` 是任务，`/manage/execution` 是执行策略。来源资产和 WMA 返回仍可人工上传，未取消手工方式。

## 从本次指定的 84353c7 升级

保留原 `deepaha-data`，不要复制测试数据库过去。启动器会先检查原各阶段结构和账号表，再调用 `upgrade-experience`。本次新增五张表，原机会、审核记录、账号密码不回写；迁移前先在线 SQLite 备份并校验，失败会停止启动。已有 RUNNING 任务时拒绝升级，必须先查清远端状态，不能只杀进程后把它当成已经结束。

命令行显式升级（已安装当前包依赖时）：

```powershell
$env:PYTHONPATH = "$PWD\backend\src"
$env:DEEPAHA_DATA_DIR = "$env:USERPROFILE\deepaha-data"
python -m deepaha.product.cli upgrade-experience
```

成功回执列出实际备份路径和新增表。重复执行返回 `already_current`，不重复迁移。备份请复制到另一个可靠存储位置；**有备份文件不等于已经做过恢复演练**。

独立本地试运行可先指定另一个空目录，避免触及原数据：

```powershell
$env:DEEPAHA_DATA_DIR = "$env:USERPROFILE\deepaha-experience-trial"
py -3.13 scripts/launch_product.py --install
```

## Linux / 明确的 CLI 方式

```bash
python3.13 -m venv .venv-product
. .venv-product/bin/activate
python -m pip install -r backend/requirements-product.txt
export PYTHONPATH="$PWD/backend/src"
export DEEPAHA_DATA_DIR="$HOME/deepaha-experience-trial"
python -m deepaha.product.cli setup
python -m deepaha.product.cli serve --host 127.0.0.1 --port 8000
```

初次 `setup` 仅用于新库；已有库使用 `upgrade-experience`，不要再创建同名账号。启用远程调查另开进程运行 `python -m deepaha.product.cli worker`，并按 WMA 文档配置宿主连接。没有 SDK 或凭据时保留未配置状态，不修改任何模型开关。

## PostgreSQL 注意

本轮没有运行 PostgreSQL。升级前 API/Worker 全停、停止新写入、先完成宿主备份和空库恢复演练。`upgrade-experience` 的 PG 分支要求 `pg_dump`/`pg_restore`，生成自定义格式 dump、对象包与哈希，先通过目录可读性检查再新增表；`pg_restore --list` **不是恢复演练**。

请保留宿主连接的原环境变量与 SSL 配置，确认备份目标确实为正确数据库。后续实际演练和双客户端并发测试全部通过、人工验收后，才允许用于线上。不要直接复用旧 SG8-A 发布脚本绕过本次增量迁移。

## 本轮依赖环境的具体限制

当前容器的基础锁定依赖匹配，但没有安装 WMA SDK；pyproject.toml 声明 pypdf>=6,<7，而容器实际为5.9.0。在线补齐尝试未成功，未改变原依赖声明来伪装环境一致。默认启动器 requirements-product.txt 与 pyproject 的 pypdf 声明亦有历史差异；发布前请按 pyproject 安装并核对依赖，重跑全部回归和 PDF 资格证据用例。本轮是现有 Linux 运行环境验证，不是全新目标环境安装验证。
