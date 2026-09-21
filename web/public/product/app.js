import {renderAccess} from './access-ui.js';
import {state,$,e,brand,icon,api,bind,toast,go,empty,enhanceControls,scrollPositions,rememberScroll,clearPrivateUI} from './core.js';
import {renderUser} from './user.js';
import {renderWork} from './workbench.js';
import {compactCount,internalPath} from './mobile-core.js';
let generation=0,cleanup=()=>{},renderedURL='',lastUser=null;

async function loginView(params){
 const next=internalPath(params.get('next')||'/app/overview');
 return {html:`<main id="main-content" class="login-page"><div class="login-card">${brand()}<h1>登录机会星图</h1><p class="login-intro">保存关注方向，继续你的收藏与准备。</p><form id="login-form"><div class="form-field"><label for="username">账号</label><input id="username" name="username" required minlength="3" maxlength="80" autocomplete="username" autocapitalize="none" spellcheck="false" enterkeyhint="next"></div><div class="form-field"><label for="password">密码</label><input id="password" type="password" name="password" required maxlength="256" autocomplete="current-password" enterkeyhint="go"></div><button class="btn primary wide" type="submit">登录</button>${state.site.registration?`<a href="/register?next=${encodeURIComponent(next)}" data-nav class="btn wide">使用邀请码注册</a>`:''}</form><a class="back-link" href="/reset-password" data-nav>忘记密码 / 使用重置码</a><a class="back-link" href="/app/overview" data-nav>先浏览机会总览</a></div></main>`,after:()=>{
  bind('#login-form','submit',async(_,f)=>{const r=await api('/api/auth/login',{method:'POST',data:Object.fromEntries(new FormData(f))});clearPrivateUI();state.user=r;state.csrf=r.csrf;go(next,true);});
 }};
}
async function updateBadge(current){
 if(!state.user||!document.querySelector('[data-unread-badge]'))return;
 try{
  const r=await api('/api/me/summary');if(current!==generation)return;
  document.querySelectorAll('[data-unread-badge]').forEach(node=>{node.textContent=compactCount(r.unread_count);node.hidden=!r.unread_count;});
  document.querySelectorAll('[data-message-link]').forEach(node=>node.setAttribute('aria-label',r.unread_count?`消息，${r.unread_count} 条未读`:'消息'));
 }catch{/* The page remains usable; do not fabricate a zero unread count. */}
}
async function render(){
 const current=++generation,path=location.pathname,params=new URLSearchParams(location.search),url=path+location.search,app=$('#app');
 if(lastUser!==state.user?.username){clearPrivateUI();lastUser=state.user?.username;}
 document.body.classList.add('route-loading');app?.setAttribute('aria-busy','true');$('#route-status').hidden=false;
 try{
  const page=['/register','/reset-password','/account/security'].includes(path)?await renderAccess(path,params):path==='/login'?await loginView(params):path.startsWith('/review')||path.startsWith('/manage')?await renderWork(path,params):await renderUser(path,params);
  if(current!==generation)return;
  cleanup();if($('#dialog').open)$('#dialog').close();app.innerHTML=page.html;
  document.body.dataset.surface=path.startsWith('/manage')||path.startsWith('/review')?'workspace':path.startsWith('/app')?'user':'portal';
  const dispose=page.after();cleanup=typeof dispose==='function'?dispose:()=>{};enhanceControls();
  renderedURL=url;document.title=($('#main-content h1')?.textContent||'机会星图')+' · DeepAha';
  requestAnimationFrame(()=>{
   if(current!==generation)return;
   if(!params.has('focus')){const heading=$('#main-content h1')||$('#main-content');heading?.setAttribute('tabindex','-1');heading?.focus({preventScroll:true});window.scrollTo(0,scrollPositions.get(url)||0);}
  });
  void updateBadge(current);
 }catch(err){
  if(current!==generation)return;
  cleanup();cleanup=()=>{};
  if(err.status===401){state.user=null;state.csrf='';clearPrivateUI();return go('/login?next='+encodeURIComponent(url),true,true);}
  if($('#dialog').open)$('#dialog').close();
  const unavailable=[403,404,410].includes(err.status);
  app.innerHTML=`<main id="main-content" class="user-main page-error">${brand()}<section class="error-panel"><span class="empty-icon">${icon(err.status===410?'info':'globe')}</span><h1>${err.status===403?'没有访问此页面的权限':err.status===410?'这条机会已撤回':err.status===404?'这条内容暂不可用':'暂时未能读取'}</h1><p>${e(err.message)}</p><div class="row wrap gap12">${!unavailable?'<button class="btn primary" id="retry-page">重新读取</button>':''}<a class="btn" href="/app/overview" data-nav>返回机会总览</a>${state.user?'<a class="btn" href="/app/actions" data-nav>我的行动</a>':''}</div></section></main>`;
  bind('#retry-page','click',render);renderedURL=url;
 }finally{if(current===generation){document.body.classList.remove('route-loading');app?.removeAttribute('aria-busy');$('#route-status').hidden=true;}}
}
document.addEventListener('click',ev=>{const a=ev.target.closest('a[data-nav]');if(a&&!a.hasAttribute('aria-disabled')&&ev.button===0&&!ev.ctrlKey&&!ev.metaKey&&!ev.shiftKey&&!ev.altKey){ev.preventDefault();go(a.getAttribute('href'));}});
window.addEventListener('routechange',render);
window.addEventListener('popstate',()=>{if(renderedURL)rememberScroll(renderedURL);render();});
const visual=()=>{const v=window.visualViewport;document.documentElement.style.setProperty('--visual-height',(v?.height||innerHeight)+'px');document.documentElement.style.setProperty('--visual-top',(v?.offsetTop||0)+'px');};
window.visualViewport?.addEventListener('resize',visual);window.visualViewport?.addEventListener('scroll',visual);window.addEventListener('resize',visual);visual();
window.addEventListener('offline',()=>{$('#network-notice').hidden=false;});
window.addEventListener('online',()=>{$('#network-notice').hidden=true;toast('连接已恢复，未自动重复提交任何操作');});
window.addEventListener('productupdated',()=>{$('#release-notice').hidden=false;});
$('#reload-release').onclick=()=>window.location.reload();
try{state.site=await api('/api/site');}catch{ /* Public shell can still load without pretending account APIs succeeded. */ }
try{state.user=await api('/api/auth/me');state.csrf=state.user.csrf;}catch{}
await render();
