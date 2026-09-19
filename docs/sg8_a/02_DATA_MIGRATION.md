# SG8-A｜本地 SQLite → 服务器 PostgreSQL

## 1. 为什么不用“复制 deepaha.db 到服务器”

公网生产模式明确要求 PostgreSQL。Windows SQLite 继续作为本地开发/验收库，不直接成为公网长期生产库。

## 2. 本地导出

在 **SG8-A 代码目录**双击：

`script/export-sg8a-portable.cmd`（实际文件：`scripts/export-sg8a-portable.cmd`）

脚本会：

1. 仅停止本启动器管理的本地 API/Worker；
2. 调用现有 `backup`；
3. 立即 `verify-backup`；
4. 输出 `sg8a-export/DeepAha-local-时间.zip`。

该备份包含账号密码哈希、用户画像、审核结果和原件，因此是**敏感文件**；但不包含 WMA API Key。

## 3. 服务器迁移

服务器先创建**空 PostgreSQL 数据库**和空数据目录，然后：

```bash
sudo bash ops/sg8a/install-release.sh staging /path/to/extracted-sg8a \
  --sqlite-backup /secure/path/DeepAha-local-....zip
```

内部实际执行：

```bash
python -m deepaha.product.cli migrate-sqlite-backup BACKUP.zip
```

迁移约束：

- 源必须是 `verify-backup` 已通过的 DeepAha SQLite backup；
- 目标数据库必须没有 DeepAha 数据；
- 目标原件目录必须没有文件；
- 逐表使用 SQLAlchemy 类型化复制；
- 迁移后比较每张表的 row count + canonical SHA256；
- 原件逐文件 SHA256 再校验；
- 本地 browser sessions 被撤销；
- worker heartbeat 被清除；
- WMA 凭据不迁移，服务器重新从 `/etc/deepaha/*.env` 注入。

## 4. staging 与 production

第一轮可以用同一份本地备份分别初始化两个**独立空库**。之后 staging 与 production 各自演进，不能再通过覆盖数据库“同步”。

## 5. 真实 PostgreSQL 验收

本交付容器没有 PostgreSQL server/psycopg，因此只完成了：

- 迁移算法完整代码；
- SQLite→SQLite 同一 SQLAlchemy 类型化复制路径的完整自测；
- 41 张表、对象文件、session 撤销、非空目标拒绝等测试。

**第一次 PostgreSQL 真迁移必须在 staging 先完成并保存迁移 report；只有 staging 校验通过才允许 production。**
