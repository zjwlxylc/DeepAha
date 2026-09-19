import fs from 'node:fs';
const user=fs.readFileSync(new URL('../public/product/user.js',import.meta.url),'utf8');
const workbench=fs.readFileSync(new URL('../public/product/workbench.js',import.meta.url),'utf8');
const api=fs.readFileSync(new URL('../../backend/src/deepaha/product/api.py',import.meta.url),'utf8');
const cli=fs.readFileSync(new URL('../../backend/src/deepaha/product/cli.py',import.meta.url),'utf8');
const launch=fs.readFileSync(new URL('../../scripts/launch_product.py',import.meta.url),'utf8');
const must=[
 [user,'行动时间线'],[user,'本周机会摘要'],[user,'最终结果'],[user,'截止提醒'],[user,'机会变化'],[user,'每周机会摘要'],
 [workbench,'反馈样本'],[workbench,'/api/manage/feedback-candidates'],
 [api,'/api/me/actions/{id}/history'],[api,'/api/me/weekly-digest'],[api,'/api/manage/feedback-candidates'],
 [cli,'upgrade-sg6'],[launch,'upgrade-sg6'],
];
for(const [src,needle] of must){if(!src.includes(needle)){console.error('MISSING',needle);process.exit(1)}}
console.log('SG6_ACTION_FEEDBACK_LOOP=PASS');
