import fs from 'node:fs';
const core=fs.readFileSync(new URL('../public/product/core.js',import.meta.url),'utf8');
const user=fs.readFileSync(new URL('../public/product/user.js',import.meta.url),'utf8');
const workbench=fs.readFileSync(new URL('../public/product/workbench.js',import.meta.url),'utf8');
const api=fs.readFileSync(new URL('../../backend/src/deepaha/product/api.py',import.meta.url),'utf8');
const cli=fs.readFileSync(new URL('../../backend/src/deepaha/product/cli.py',import.meta.url),'utf8');
const launch=fs.readFileSync(new URL('../../scripts/launch_product.py',import.meta.url),'utf8');
const must=[
 [core,'actionTime'],[core,'primary_milestone'],[core,'time_readiness'],[core,'滚动受理'],
 [user,'actionTime'],[user,'关键截止尚不能安全用于提醒'],
 [workbench,'按公告'],[workbench,'按具体机会'],[workbench,'时间待确认'],[workbench,'已过截止'],
 [workbench,'/api/review/catalog/summary'],[workbench,'/api/review/catalog/groups'],[workbench,'/api/review/catalog/targets'],
 [api,'/api/review/catalog/summary'],[api,'/api/review/catalog/groups'],[api,'/api/review/catalog/targets'],
 [cli,'upgrade-sg5-1'],[launch,'upgrade-sg5-1'],
];
for(const [src,needle] of must){if(!src.includes(needle)){console.error('MISSING',needle);process.exit(1)}}
console.log('SG5_1_TIME_AND_CATALOG_WORKSPACE=PASS');
