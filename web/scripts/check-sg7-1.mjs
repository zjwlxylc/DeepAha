import fs from 'node:fs';
const lab=fs.readFileSync('public/product/lab-ui.js','utf8');
const checks=[
 ['V2 twin surface',lab,'V${twins.items?.[0]?.version||2}'],
 ['independent deterministic oracle wording',lab,'自动测试与真人反馈分别统计'],
 ['engineering gold is not human gold',lab,'工程样本不计入独立人工评估'],
 ['SG7.1 safety label',lab,'实验结果仅用于评估，不改变正式收录或资格判断'],
];
for(const [label,body,needle] of checks){if(!body.includes(needle))throw new Error(`SG7.1 check failed: ${label}`)}
console.log('SG7_1_INDEPENDENT_GOLD_AND_TWIN_V2=PASS');
