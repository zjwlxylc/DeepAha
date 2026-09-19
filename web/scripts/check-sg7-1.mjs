import fs from 'node:fs';
const lab=fs.readFileSync('public/product/lab-ui.js','utf8');
const checks=[
 ['V2 twin surface',lab,'V${twins.items?.[0]?.version||2}'],
 ['independent deterministic oracle wording',lab,'确定性标准答案判卷'],
 ['engineering gold is not human gold',lab,'工程标准答案不等于独立人工 Gold'],
 ['SG7.1 safety label',lab,'SG7.1 不是旧 Gold 收录门'],
];
for(const [label,body,needle] of checks){if(!body.includes(needle))throw new Error(`SG7.1 check failed: ${label}`)}
console.log('SG7_1_INDEPENDENT_GOLD_AND_TWIN_V2=PASS');
