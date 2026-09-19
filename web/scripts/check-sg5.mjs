import fs from 'node:fs';
const user=fs.readFileSync(new URL('../public/product/user.js',import.meta.url),'utf8');
const css=fs.readFileSync(new URL('../public/product/product.css',import.meta.url),'utf8');
const api=fs.readFileSync(new URL('../../backend/src/deepaha/product/api.py',import.meta.url),'utf8');
const personal=fs.readFileSync(new URL('../../backend/src/deepaha/product/personal.py',import.meta.url),'utf8');
const must=[
  [api,"/api/me/value/{id}"],
  [personal,'LOCAL_VALUE_PRIORITY_V1'],
  [user,'今天真正值得你看的'],
  [user,'为什么值得我关注'],
  [user,'为什么现在'],
  [user,'关闭个性化机会排序'],
  [user,'opportunity_types'],
  [user,'career_directions'],
  [user,'region_preference_mode'],
  [user,'personalization_enabled'],
  [css,'.star-featured'],
  [css,'.value-explanation'],
];
for(const [text,needle] of must){if(!text.includes(needle)){console.error('MISSING',needle);process.exit(1)}}
for(const forbidden of ['匹配度 92%','成功率 92%','match_percent']){if(user.includes(forbidden)){console.error('FORBIDDEN',forbidden);process.exit(1)}}
console.log('SG5_FRONTEND_CONTRACT=PASS');
