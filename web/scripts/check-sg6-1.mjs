import fs from 'node:fs';
const user=fs.readFileSync(new URL('../public/product/user.js',import.meta.url),'utf8');
const work=fs.readFileSync(new URL('../public/product/workbench.js',import.meta.url),'utf8');
const css=fs.readFileSync(new URL('../public/product/product.css',import.meta.url),'utf8');
const brand=fs.readFileSync(new URL('../public/product/brand-v2.css',import.meta.url),'utf8');
const app=fs.readFileSync(new URL('../public/product/app.js',import.meta.url),'utf8');
const must=[
 [user,'/app/actions'],[user,'收藏与行动'],[user,'desktop-main-nav'],[user,'desktop-user-nav'],
 [user,'action-summary'],[user,"api('/api/me/actions')"],[user,'aria-current'],
 [work,'审核工作台'],[work,'系统管理'],[work,'workspace-section-label'],[work,'aria-current'],
 [brand,'--space-1'],[brand,'--radius-md'],[brand,'--shadow-sm'],[brand,'--focus-ring'],
 [css,'.desktop-main-nav'],[css,'.action-summary'],[css,'.form-help'],[css,'.field-error'],
 [css,'@media (prefers-reduced-motion:reduce)'],[css,'min-height:44px'],[css,'.skip-link:focus'],
 [app,'route-loading'],[app,"setAttribute('aria-busy'"],
];
for(const [src,needle] of must){if(!src.includes(needle)){console.error('MISSING',needle);process.exit(1)}}
console.log('SG6_1_UI_UX_CONTRACT=PASS');
