# SG4 Eligibility Delivery

基线：用户人工验收通过的 3.3.0-rc1 / SG3。

实现：新增 `deepaha.product.eligibility` Computation Lane；扩展个人画像；保持 `/api/me/fit/{id}` 路径稳定并返回逐条件 Evidence；移动端增加四态与 Evidence 展开；增加 openpyxl 作为保存 XLSX 的受控读取依赖。

无数据库 Schema 迁移。没有恢复旧逐字段核验、方法认证或规则审批前置；没有实现 SG5 Value/Priority。

真实验证使用用户最初上传 RC2 WMA 数据的副本：106 Target 不变；综合管理编号1对本科/050303画像形成由保存 XLSX K5/M5支持的明确冲突；旧权威表摘要和对象树哈希不变。
