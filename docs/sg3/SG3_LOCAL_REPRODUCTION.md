# SG3 Windows 本地复现说明

完整操作见 [`00_START_HERE.md`](00_START_HERE.md)。

最简路径：

1. 保留 `C:\Users\LENOVO\deepaha-data`，用 3.3.0-rc1 源码启动，确认真实总览仍为 106 岗位；
2. 新建 `C:\Users\LENOVO\deepaha-data-sg3-test`；
3. 初始化账号和虚构来源 `https://research.example.org/`；
4. 导入并整体通过 `01_initial.zip`；
5. 导入 `02_deadline_extension_A01.zip`，先不要通过；
6. 核对 A01 UPDATE_PENDING、A02 CURRENT；
7. 整体通过，核对 A01 截止变为 2026-12-05，并能查看版本历史；
8. 在独立干净测试环境分别验证 missing、child withdrawal、root withdrawal。

所有 `examples/sg3-currentness/` 数据均为虚构体验数据，不会自动导入正式数据库。
