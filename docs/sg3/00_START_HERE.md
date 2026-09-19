# SG3 本地验收入口

版本：**3.3.0-rc1 / SG3 版本、变化与当前性**

前置条件：SG1、SG2 均已由用户人工验收通过。本轮只解决机会已经进入总览以后，官方发生**更正、延期、撤回、附件替换、部分返回缺失**时，DeepAha 如何精确更新当前状态并保留历史；不进入 SG4 Eligibility、SG5 个性排序或支付。

## 先验证你的真实 106 岗位没有回归

继续使用：

`C:\Users\LENOVO\deepaha-data`

SG3 **没有新增数据库 Schema 迁移**。如果该目录已经通过 SG1/SG2，直接换成 3.3.0-rc1 源码启动即可。

打开：

`http://127.0.0.1:8000/app/overview`

你原来的真实 WMA 招聘结果应继续保持 **106 个具体岗位**。SG3 不会重新调用 WMA，不会自动重新审核，也不会把旧岗位误判为撤回。

## 再用独立测试目录体验 SG3

建议建立：

`C:\Users\LENOVO\deepaha-data-sg3-test`

不要把下面的虚构包导入正式数据目录。

仓库附带：

- `examples/sg3-currentness/01_initial.zip`：A01/A02 初始版；
- `02_deadline_extension_A01.zip`：只延期 A01；
- `03_attachment_replacement_A01.zip`：只替换 A01 证据附件；
- `04_missing_A02_not_withdrawn.zip`：新版未出现 A02，用于验证“缺失≠撤回”；
- `05_explicit_withdraw_A01.zip`：明确撤回 A01；
- `06_root_withdrawal.zip`：明确撤回整份父机会。

### 初始化独立体验环境

在本代码目录打开 PowerShell：

```powershell
$env:DEEPAHA_DATA_DIR='C:\Users\LENOVO\deepaha-data-sg3-test'
$env:PYTHONPATH="$PWD\backend\src"
py -3.13 -m deepaha.product.cli setup
py -3.13 -m deepaha.product.cli source-add --actor owner --name "海湾研究中心（虚构）" --url "https://research.example.org/" --allowed-host research.example.org
py -3.13 scripts\launch_product.py --install
```

如果你的管理员账号不是 `owner`，把 `--actor owner` 换成实际维护账号。

### 场景 A：延期只影响 A01

1. 进入审核工作台，点击 **导入返回**，选择 `01_initial.zip`；
2. 整体通过；
3. 在机会总览找到 A01、A02；可先收藏 A01/A02 并设置截止提醒；
4. 再导入 `02_deadline_extension_A01.zip`；
5. 暂时不要通过，先看审核页与用户页。

此时应看到：

- 审核页显示 **变化 1、未变化 1**；
- A01 显示“有更新待收录”，旧截止日期不再作为可执行提醒使用；
- A02 仍保持 `CURRENT`，截止日期仍是 `2026-11-20`；
- A02 的提醒不应因为 A01 延期而取消；
- 审核员可对 A01 创建 **定向复查**，任务范围只包含 A01 和受影响字段。

整体通过第二版后：

- A01 当前截止变为 `2026-12-05`；
- A02 不变；
- A01 详情可以看到至少两条版本记录；
- 历史对比能看到 `2026-11-10 → 2026-12-05`。

### 场景 B：新版没出现，不等于撤回

建议重新使用一个干净测试目录，先通过 `01_initial.zip`，再导入 `04_missing_A02_not_withdrawn.zip`。

应看到：

- A02 标记为**更新待确认 / 本轮未出现**；
- A02 不应自动变成 WITHDRAWN；
- 即使整体通过该返回，A02 仍保留为待确认，不被静默删除。

### 场景 C：明确撤回具体机会

同样从初始版开始，再导入 `05_explicit_withdraw_A01.zip`。

整体通过前：A01 是撤回待收录；A02 正常。

整体通过后：

- A01 从当前机会总览退出；
- A02 继续存在；
- A01 历史仍可追溯；
- 不得把父公告和 A02 一起撤回。

### 场景 D：整份机会明确撤回

从初始版开始，再导入 `06_root_withdrawal.zip` 并整体通过。

此时该父机会下全部当前行动目标退出当前总览，但历史版本和审核记录继续保留。

## 本轮人工验收重点

建议至少确认：

- [ ] 真实 106 岗位仍是 106 个；
- [ ] 只延期 A01 时，A02 完全不受影响；
- [ ] 变化待收录时，受影响旧截止不会继续产生有效提醒；
- [ ] 通过延期后，A01 展示新截止及版本记录；
- [ ] “新版没出现 A02”不会自动撤回 A02；
- [ ] 明确撤回 A01 只撤 A01；
- [ ] 明确撤回 Root 才撤全部后代；
- [ ] 定向复查只包含被影响的目标/字段；
- [ ] 用户页面不暴露内部 `lifecycle_status` 等技术字段。

SG3 人工验收通过前，不进入 SG4。
