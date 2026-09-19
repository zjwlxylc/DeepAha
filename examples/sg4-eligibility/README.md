# SG4 Eligibility 虚构验收样本

这些 ZIP 全部是**虚构本地测试数据**，不会自动导入。建议使用单独的数据目录 `C:\Users\LENOVO\deepaha-data-sg4-test`，不要导入正式库。

先在 DeepAha 中登记来源 `海湾研究中心（虚构）`，入口 `https://research.example.org/`，然后逐个上传并整体通过。

建议画像：学历=本科，专业=广告学，专业代码=050303，毕业年份=2027，户籍地区=浙江省宁波市。

- `01_eligible_complete.zip` → `ELIGIBLE`：明确覆盖的硬条件均有当前证据且符合。
- `02_ineligible_xlsx.zip` → `INELIGIBLE`：学历和专业代码与 XLSX K5/M5 的硬条件冲突。
- `03_uncertain_exception.zip` → `UNCERTAIN`：含例外与未实现的复杂硬条件，系统不得猜测。
- `04_likely_bounded.zip` → `LIKELY_ELIGIBLE`：已知可计算条件符合，但材料未声明资格覆盖完整。

这些样本只验证 SG4 “Can I?”，不代表机会价值、推荐优先级或录取概率。
