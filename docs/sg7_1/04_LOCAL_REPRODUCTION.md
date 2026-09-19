# SG7.1 Windows 本地复现与人工验收

版本：**DeepAha 3.7.1-rc1 / SG7.1**

## 1. 升级方式

1. 停止 3.7.0 或更早版本 API / Worker；
2. 保留原数据目录：`C:\Users\LENOVO\deepaha-data`；
3. 将 3.7.1 ZIP 解压到新程序目录，不覆盖唯一旧源码副本；
4. 双击 `启动机会星图.cmd`。

启动器仍执行既有升级链，最后运行 `upgrade-sg7`。SG7.1 将实验层 meta 升为 V2；SQLite 会 backup-first。

如果你的数据目录曾运行 3.7.0：

- V1 Twin / Pair Truth / Run 历史不会删除；
- V1 Twin 会退出 active 集；
- 进入“工作台 → 机会实验室”后点击“生成 100 个数字分身”，应得到 **V2 · 100/100**。

## 2. 先做回归观察

确认 SG6.2 原有行为不变：

- 原采集/WMA结果、审核通过、正式机会仍在；
- reviewer 仍只有整体通过/不通过；
- 明确学历等硬冲突仍可 INELIGIBLE；
- 高风险但证据不足仍保持 UNCERTAIN + HOLD；
- 收藏、行动、反馈正常；
- reviewer/operator 权限隔离正常。

## 3. SG7.1 界面重点

`工作台 → 机会实验室`：

- 数字分身区域应显示 `V2 · 100/100`；
- 页面明确说明“工程确定性标准答案 ≠ 独立人工 Gold”；
- Gold/Pair Truth 仍是实验资产，不是审核/事实晋升入口；
- Gold Benchmark 不应把显式机会类型不匹配、STRICT地区不匹配的 Pair 升成 FEATURE。

## 4. 可选：本地重跑独立标准答案

进入解压目录后，在已安装测试依赖的终端执行：

```powershell
$env:PYTHONPATH = "$PWD\backend\src"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest -q -s -p pytest_asyncio.plugin `
  backend/tests/product/test_sg7_independent_oracle100.py `
  backend/tests/product/test_sg7_recommendation_oracle100.py
```

应看到两个测试 PASS，并输出：

- Eligibility：600 pairs，accuracy 1.0；
- Recommendation：2000 pairs，accuracy 1.0；
- unsafe = 0；
- LLM/WMA 未调用；
- production_mutated = false。

## 5. 仍需人工判断的内容

工程 Oracle 不能回答：

> “真实青年是否觉得推荐值得行动？”

所以你本地验收主要看：

- 机会实验室是否能理解、可操作；
- 100 V2 Twin 分布是否合理；
- 实验界面是否清楚区分工程 Gold / 人工 Gold / 真人反馈；
- 主产品有无回归。

只有你明确确认 **“SG7.1 人工验收通过”** 后，3.7.1-rc1 才成为下一阶段代码基线。
