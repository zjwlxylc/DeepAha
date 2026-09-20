import {spawnSync} from 'node:child_process';
import {readdirSync,readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../public/product/',import.meta.url));
for(const name of readdirSync(root).filter(x=>x.endsWith('.js'))){const r=spawnSync(process.execPath,['--check',root+name],{stdio:'inherit'});if(r.status)process.exit(r.status);}
for(const name of ['app.js','core.js','user.js','workbench.js','scout.js']){const s=readFileSync(root+name,'utf8');if(/localStorage|sessionStorage|fixtures\.js/.test(s))throw new Error('Business fixture/persistence code in '+name);}

const core=readFileSync(root+'core.js','utf8'),user=readFileSync(root+'user.js','utf8'),workbench=readFileSync(root+'workbench.js','utf8');
for(const [name,source,needles] of [
 ['core.js',core,['targetKinds','parent_announcement','编号 ']],
 ['user.js',user,['公告共同条件','单位 / 分组共同内容','收藏这项具体机会','/app/announcement/','scope-more']],
 ['workbench.js',workbench,['action_targets','catalog_target_ids','预计进入总览的具体机会','child(c,o.type,o.raw_type)']],
]){
 for(const needle of needles)if(!source.includes(needle))throw new Error(`SG1 actionable UI contract missing in ${name}: ${needle}`);
}
if(workbench.includes('receipt.public_ids.slice(item,item+1)'))throw new Error('Review receipt still navigates to root announcement instead of actionable target');

for(const [name,source,needles] of [
 ['core.js',core,['presentation?.target_label','presentation?.time_label','presentation?.type_label']],
 ['user.js',user,['presentation?.own_section_title','presentation?.ancestor_section_title','presentation?.common_section_title','presentation?.parent_label','presentation?.action_label','POSTGRAD_RECOMMENDATION']],
]){
 for(const needle of needles)if(!source.includes(needle))throw new Error(`SG2 multi-type UI contract missing in ${name}: ${needle}`);
}


for(const [name,source,needles] of [
 ['user.js',user,['currentness-banner','更新记录','/history','更新待收录']],
 ['workbench.js',workbench,['变更范围','currentness','定向复查','撤回具体机会']],
]){
 for(const needle of needles)if(!source.includes(needle))throw new Error(`SG3 currentness UI contract missing in ${name}: ${needle}`);
}


for(const [name,source,needles] of [
 ['user.js',user,['major_code','birth_date','hukou_region','当前条件明确符合','发现明确不符合条件','查看最新官方条件','查看资格依据']],
]){
 for(const needle of needles)if(!source.includes(needle))throw new Error(`SG4 eligibility UI contract missing in ${name}: ${needle}`);
}

console.log('Product JavaScript syntax, no-fixture, SG1 actionable, SG2 multi-type, SG3 currentness, and SG4 eligibility UI checks passed');
