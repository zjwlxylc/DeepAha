# SG4 Windows 本地复现

1. 停止旧 DeepAha。
2. 将本 ZIP 解压到新的程序目录，不覆盖唯一旧副本。
3. 保留 `C:\Users\LENOVO\deepaha-data`。
4. 双击 `启动机会星图.cmd`。
5. 打开 `http://127.0.0.1:8000/app/overview`，确认真实机会仍是 106 个岗位。
6. 进入“我的关注方向”，补充资格画像；打开具体岗位点击“适合我吗”。

SG4 没有新增 DB Schema 迁移，也不会为了资格判断重新调用 WMA。

要体验四态，请另设测试数据目录并使用 `examples/sg4-eligibility/`，操作详见该目录 README。
