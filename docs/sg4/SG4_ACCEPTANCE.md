# SG4 Gate D 验收

SG4 只有以下条件全部成立才可人工验收：

1. `INELIGIBLE` 每一项 hard conflict 都有当前、可定位 Evidence 和确定性比较；
2. 同一硬条件 Evidence 未定位时必须退回 UNCERTAIN；
3. 例外、OR、相关专业、通用应届生等复杂语义不得产生硬否定；
4. 保存 XLSX 单元格可以复核，损坏 XLSX 不得 500；
5. SG3 受影响字段更新待收录时不得产生旧版本否定；
6. 用户画像不发送 WMA/外部模型；
7. SG1/SG2/SG3 全部回归保持通过；
8. 用户真实 RC2 数据回放仍为 58 GROUP + 106 POSITION → 106 Target，旧权威表与对象原件不变；
9. 四态本地虚构样本可复现；
10. 不进入 SG5 Value/Priority。
