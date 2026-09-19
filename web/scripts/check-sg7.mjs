import fs from 'node:fs';
const files={
  lab:fs.readFileSync('public/product/lab-ui.js','utf8'),
  user:fs.readFileSync('public/product/user.js','utf8'),
  work:fs.readFileSync('public/product/workbench.js','utf8'),
  css:fs.readFileSync('public/product/product.css','utf8'),
};
const need=[
 ['operator lab route',files.work,"'/manage/lab'"],
 ['user lab route',files.user,"path==='/app/lab'"],
 ['voluntary join',files.lab,'自愿加入共创实验'],
 ['withdraw',files.lab,'退出共创实验'],
 ['pair truth',files.lab,'机会 × 数字分身评估真值'],
 ['real gold boundary',files.lab,'不算真人 Gold'],
 ['WMA privacy',files.lab,'不会把你的完整画像发给 WMA'],
 ['aggregate privacy',files.lab,'只显示聚合统计'],
 ['lab responsive css',files.css,'.lab-metrics'],
];
for(const [label,body,needle] of need){if(!body.includes(needle))throw new Error(`SG7 check failed: ${label}`)}
for(const bad of ['确认学历字段','确认专业字段','确认年龄字段','事实晋升按钮']){
 if(Object.values(files).some(x=>x.includes(bad)))throw new Error(`SG7 restored retired field-review wording: ${bad}`);
}
console.log('SG7 frontend contract: PASS');
