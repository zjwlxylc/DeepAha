# DeepAha SG7 本地复现说明

本包为 **3.7.0-rc1 / SG7 Opportunity Lab** 本地人工验收候选。

最重要的操作：

1. 保留 `C:\Users\LENOVO\deepaha-data`；
2. SG7 ZIP 解压到新目录，不覆盖唯一 SG6.2 源码备份；
3. 停止旧服务后双击 `启动机会星图.cmd`；
4. 首次启动会 backup-first 执行 `upgrade-sg7`；
5. SG7 不重新调用 WMA，不改已有正式机会/审核/资格/行动数据；
6. 先复查 SG6.2 核心行为，再查看 `工作台 → 机会实验室` 与 `我的 → 机会共创实验`；
7. 完整验收步骤见 `docs/sg7/04_LOCAL_REPRODUCTION.md`。

工程自测：26 个产品测试文件 / 216 tests 全部 RC=0；前端合同与真实 HTTP Smoke 通过。最终 UI/Windows 操作感受仍以你的本地人工验收为准。
