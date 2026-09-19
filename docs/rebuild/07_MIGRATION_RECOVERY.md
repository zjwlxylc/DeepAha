# 迁移、备份、恢复与回退

## 1. 不覆盖原系统
本包是隔离副本，不是已合入远程主线的补丁。原归档基线和观测远程main不同；先比较你当前分支与 `evidence/source-diff.json`，保留本机未提交更改，不能把ZIP直接覆盖到已部署目录或把原数据库删掉重建。

默认新数据目录，只创建新库。当前SQL映射保留既有sources/opportunities身份列；新业务表使用product前缀。初始化 `create_all` 只创建缺表，不修改已应用Alembic迁移；产品schema版本当前为1。**这不是已完成旧生产库迁移的证明。** 原PG约束、触发器、角色、迁移head须在副本对照验证后才能采用。

## 2. 推荐迁移顺序
先备份旧数据库与原件、记录代码/迁移/配置。用原数据库副本进行只读inventory，保留旧审核责任含义。完成新产品表的副本初始化，创建真实密码账号或后续接入部署身份，不能把旧fixture Cookie放行成生产身份。

旧来源通过受控source-add采用现有canonical_url，保持Source ID。旧机会需要已确认关联时，先执行：
```bash
python -m deepaha.product.cli identity-adopt --source SOURCE_ID --notice-url https://allowed.example.org/notices/123 --public-id OLD_PUBLIC_ID --actor maintainer01
```
实际生产者有稳定source_record_key时加同值参数。此命令不发布内容、不确认事实；来源键已关联其他对象则拒绝覆盖。不要把栏目首页/同名标题当成唯一公告身份。完成确认映射后再导入对应返回，新的整体批准沿用原ID。没有可靠关联则不能宣称自动连续。

## 3. 旧返回恢复
```bash
python -m deepaha.product.cli legacy-inventory --output legacy-inventory.json
python -m deepaha.product.cli legacy-export OLD_TASK_UUID --object-root OLD_OBJECT_DIRECTORY --bucket deepaha-raw --output recovered.zip
```
以上操作通过反射只读旧表，导出已保存结果和可定位原件，并检查哈希；不调用旧Provider或重跑WMA。未存原结果、原路径未知、附件同名冲突时明确失败，不能凭摘要重新造原文件。本轮未取得真人旧库及对象目录，实际导出仍须在副本实测。

将导出包导入新收件箱后，需要真人重新作一次整体决定。旧逐字段HUMAN记录或内部接收决定不自动升级为当前批准。

## 4. 本地备份与实际测试过的恢复
停止Worker后备份（原件只追加，但停写便于整体验证）：
```bash
python -m deepaha.product.cli backup /safe/backups/deepaha-20260916.zip
python -m deepaha.product.cli verify-backup /safe/backups/deepaha-20260916.zip
python -m deepaha.product.cli restore-backup /safe/backups/deepaha-20260916.zip --target /safe/restored-deepaha
```
恢复目录必须不存在。备份包含SQLite一致性快照、原件和逐文件哈希，不包含WMA连接密钥；**包含账号密码哈希和用户数据**，仍是敏感备份，不能放公开下载目录。恢复先校验目录/哈希，再恢复到新目录，撤销旧会话，清理旧Worker心跳。改 DEEPAHA_DATA_DIR 指向新目录后重新注入WMA凭据，再启动。

此链已用隔离数据库实际验证，不代表已对你现有数据库备份/恢复。恢复上限20GiB，超限使用经过验证的宿主备份工具，不扩展成在线一键清库平台。

## 5. PostgreSQL备份
采用宿主`pg_dump`自定义格式与原件卷快照，并在隔离空库用`pg_restore`演练。保留完整版本和角色/扩展要求，不把SQLite备份导入PG当自动迁移。相关官方参考已列在资料来源文件；本轮没有运行PG实例，不能将示例命令算成验证。

## 6. 回退
先停当前Worker与入口，不删新决定/原件/账户数据。恢复旧服务只能面向已经批准的旧版本，不自动恢复撤回内容；旧数据生产路径已经明确退役，回退不应重新启动旧Provider任务。真正回退发布范围由负责人决定，不能靠“保证有数据”恢复错误条目。

## 7. 必须保留的历史
原始返回、旧决定、版本、Stable ID、来源暂停记录、失败回执、外部研究资产都保留。只有确认没有运行依赖的旧专用代码才可在后续短分支删除；本包没有用大规模删源码来冒充完成重构。
