# DeepAha SG7.1 本地复现说明

本包为 **3.7.1-rc1 / SG7.1** 本地人工验收候选，基于你要求的 **3.7.0-rc1** 完成核心可信度修正。

最简单操作：

1. 保留 `C:\Users\LENOVO\deepaha-data`；
2. 解压到新程序目录；
3. 停止旧版服务；
4. 双击 `启动机会星图.cmd`；
5. 首次启动 backup-first 升级实验层 V1 → V2；
6. 打开 `工作台 → 机会实验室`，点击生成数字分身，应看到 `V2 · 100/100`；
7. 重点观察 Gold Benchmark、Pair Truth、共创实验以及 SG6.2 原功能是否回归。

SG7.1 不重新调用 WMA，不修改正式机会/审核/资格/行动数据。

本次工程标准答案：

- 资格：600/600；
- 推荐：2000/2000；
- unsafe=0；
- 28 个产品测试文件 / 219 tests 全部独立 RC=0；
- 真实 HTTP Smoke PASS。

完整步骤：`docs/sg7_1/04_LOCAL_REPRODUCTION.md`。
