# DeepAha 3.4.0-rc1 — SG4

## 新增
- 独立 `deepaha.product.eligibility` Computation Lane。
- 四态资格结果：`ELIGIBLE / LIKELY_ELIGIBLE / UNCERTAIN / INELIGIBLE`。
- Evidence-backed 确定性资格条件：学历、明确毕业届别、明确专业代码、年龄出生日期映射、户籍地区、报名窗口。
- 保存 XLSX 的 Sheet/Row/Column 单元格证据复核；损坏或无法读取时 fail closed。
- 用户画像可选 `major_code / birth_date / hukou_region`。
- 手机“适合我吗”展示逐条件结论和可展开官方依据。
- SG4 四态虚构本地验收包与真实 106 岗位回归证据。

## 安全边界
- WMA `CONFIRMED` 本身不产生硬资格结论。
- `INELIGIBLE` 只允许来自当前、已定位 Evidence 支持的确定性硬冲突。
- 例外、相关专业、通用“应届毕业生”、未知条件、证据未定位、损坏 XLSX、受影响的 `UPDATE_PENDING` 字段都保持 `UNCERTAIN`。
- 父公告年龄解释不作为全体子岗位的全局年龄条件；跨字段年龄计算要求岗位条件和父级解释两侧证据同时可定位。
- 不恢复逐字段人工批准，不调用 LLM 做资格落锤，不进入 SG5 Value/Priority。

## 数据库
无新增数据库 Schema 迁移。SG1/SG2/SG3 数据可直接继续使用。
