import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../public/product/',import.meta.url));
const user=fs.readFileSync(root+'user.js','utf8');
const core=fs.readFileSync(root+'core.js','utf8');
const css=fs.readFileSync(root+'product.css','utf8');
const html=fs.readFileSync(root+'index.html','utf8');
const checks=[
 ['uploaded brand logo',core,'/product/brand-logo.png'],
 ['homepage promise',user,'让属于你的机会，'],
 ['homepage process',user,'它怎样替你找到机会'],
 ['homepage judgment',user,'怎样判断你是否符合'],
 ['homepage action',user,'怎样帮你继续行动'],
 ['about route',user,"path==='/about'"],
 ['about mission',user,'用 AI 助力青年'],
 ['about principle',user,'用户做主'],
 ['public marketing shell',user,'marketingShell'],
 ['marketing responsive css',css,'.marketing-hero'],
 ['about css',css,'.about-hero'],
 ['mobile breakpoint',css,'@media(max-width:700px)'],
 ['favicon migrated',html,'brand-logo.png'],
];
for(const [label,body,needle] of checks){if(!body.includes(needle))throw new Error(`SG7.2 check failed: ${label}`)}
const logo=root+'brand-logo.png';
if(!fs.existsSync(logo)||fs.statSync(logo).size<10000)throw new Error('SG7.2 brand logo missing or invalid');
if(user.includes('94%'))throw new Error('SG7.2 must not copy prototype pseudo-precision score');
console.log('SG7_2_PUBLIC_HOME_ABOUT_BRAND=PASS');
