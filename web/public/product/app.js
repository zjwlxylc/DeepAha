import {renderAccess} from './access-ui.js';
import {state,$,e,brand,icon,api,bind,toast,go,empty} from './core.js';
import {renderUser} from './user.js';
import {renderWork} from './workbench.js';
let generation=0;

function enhanceControls(){
 document.querySelectorAll('input,select,textarea').forEach(control=>{
  const field=control.closest('.form-field');
  const clear=()=>{control.removeAttribute('aria-invalid');const note=field?.querySelector('.field-error');if(note){const described=(control.getAttribute('aria-describedby')||'').split(/\s+/).filter(x=>x&&x!==note.id);described.length?control.setAttribute('aria-describedby',described.join(' ')):control.removeAttribute('aria-describedby');note.remove();}};
  control.addEventListener('input',clear,{once:false});control.addEventListener('change',clear,{once:false});
  control.addEventListener('invalid',()=>{
   control.setAttribute('aria-invalid','true');
   if(!field)return;let note=field.querySelector('.field-error');
   if(!note){note=document.createElement('div');note.className='field-error';note.id='field-error-'+Math.random().toString(36).slice(2);note.setAttribute('role','alert');field.appendChild(note);}
   note.textContent=control.validationMessage||'请检查这一项';const described=new Set((control.getAttribute('aria-describedby')||'').split(/\s+/).filter(Boolean));described.add(note.id);control.setAttribute('aria-describedby',[...described].join(' '));
  });
 });
}
async function loginView(params){
 const next=params.get('next')||'/app/overview';
 return {html:`<main id="main-content" class="login-page"><div class="login-card">${brand()}<h1>登录机会星图</h1><form id="login-form"><div class="form-field"><label for="username">账号</label><input id="username" name="username" required minlength="3" maxlength="80" autocomplete="username"></div><div class="form-field"><label for="password">密码</label><input id="password" type="password" name="password" required maxlength="256" autocomplete="current-password"></div><button class="btn primary wide" type="submit">登录</button>${state.site.registration?'<a href="/register" data-nav class="btn wide">使用邀请码注册</a>':''}</form><a class="back-link" href="/reset-password" data-nav>忘记密码 / 使用重置码</a><a class="back-link" href="/" data-nav>返回首页</a></div></main>`,after:()=>{
  bind('#login-form','submit',async(_,f)=>{const r=await api('/api/auth/login',{method:'POST',data:Object.fromEntries(new FormData(f))});state.user=r;state.csrf=r.csrf;go(next,true);});
 }};
}
async function render(){
 const current=++generation,path=location.pathname,params=new URLSearchParams(location.search),app=$('#app');
 document.body.classList.add('route-loading');app?.setAttribute('aria-busy','true');
 try{
  let page=['/register','/reset-password','/account/security'].includes(path)?await renderAccess(path):path==='/login'?await loginView(params):path.startsWith('/review')||path.startsWith('/manage')?await renderWork(path,params):await renderUser(path,params);
  if(current!==generation)return;
  $('#app').innerHTML=page.html;page.after();enhanceControls();window.scrollTo(0,0);
  document.title=($('#main-content h1')?.textContent||'机会星图')+' · DeepAha';
 }catch(err){
  if(current!==generation)return;
  if(err.status===401){state.user=null;state.csrf='';return go('/login?next='+encodeURIComponent(path+location.search),true);}
  $('#app').innerHTML=`<main id="main-content" class="user-main page-error">${brand()}<div class="mt24">${empty(err.status===403?'没有访问此页面的权限':err.status===410?'这条机会已撤回':'暂时无法读取',err.message,'/app/overview','返回机会总览')}</div></main>`;
 }finally{if(current===generation){document.body.classList.remove('route-loading');$('#app')?.removeAttribute('aria-busy');}}
}
document.addEventListener('click',ev=>{const a=ev.target.closest('a[data-nav]');if(a&&ev.button===0&&!ev.ctrlKey&&!ev.metaKey&&!ev.shiftKey){ev.preventDefault();go(a.getAttribute('href'));}});
window.addEventListener('routechange',render);window.addEventListener('popstate',render);
try{state.site=await api('/api/site');}catch{}
try{state.user=await api('/api/auth/me');state.csrf=state.user.csrf;}catch{}
await render();
