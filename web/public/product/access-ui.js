import {state,$,e,brand,has,time,api,bind,go,toast,modal,pagination} from './core.js';

const field=(label,name,attrs='')=>`<div class="form-field"><label for="access-${name}">${label}</label><input id="access-${name}" name="${name}" ${attrs}></div>`;
const password=field('新密码（至少4个字符）','password','type="password" required minlength="4" maxlength="256" autocomplete="new-password"');
const confirm=field('再次输入新密码','confirm','type="password" required minlength="4" maxlength="256" autocomplete="new-password"');
function checkedPassword(data){if(data.password!==data.confirm)throw new Error('两次密码不一致');delete data.confirm;return data;}
function secretBox(text){
 const box=$('#access-secret');box.hidden=false;
 box.innerHTML=`<h2>请立即保存，仅本次显示</h2><p class="muted mt8">通过可信渠道交付给受邀者。关闭页面后无法再次查看；丢失时请撤销并重新签发。</p><textarea id="access-secret-value" readonly rows="6" aria-label="一次性凭据"></textarea><button class="btn mt12" id="copy-access-secret">复制</button><button class="btn mt12" id="hide-access-secret">清除显示</button>`;
 $('#access-secret-value').value=text;box.scrollIntoView({block:'center',behavior:'smooth'});
 bind('#copy-access-secret','click',async()=>{await navigator.clipboard.writeText(text);toast('已复制，请妥善保管');});
 bind('#hide-access-secret','click',()=>{box.replaceChildren();box.hidden=true;});
}

export async function renderAccess(path){
 const security=path==='/account/security',reset=path==='/reset-password';
 if(security&&!state.user)throw Object.assign(new Error('请先登录'),{status:401});
 if(!security&&!reset&&!state.site.registration)return {html:`<main id="main-content" class="login-page"><div class="login-card access-card">${brand()}<h1>注册暂未开放</h1><p>已有账号仍可登录，请联系邀请人了解下一批体验安排。</p><a href="/login" data-nav>返回登录</a></div></main>`,after:()=>{}};
 const title=security?'账号安全':reset?'重置密码':'受邀加入机会星图';
 const inputs=security?field('原密码','old_password','type="password" required maxlength="256" autocomplete="current-password"'):reset?field('一次性重置码','code','required maxlength="128" autocomplete="off"'):field('邀请码','invite_code','required minlength="4" maxlength="128" placeholder="输入4位邀请码" autocomplete="off"')+field('账号（英文、数字或 _.@-）','username','required minlength="3" maxlength="80" pattern="[a-zA-Z0-9_.@\\-]+" autocomplete="username"');
 return {html:`<main id="main-content" class="login-page"><div class="login-card access-card">${brand()}<h1>${title}</h1><p class="muted mt12">${security?'修改密码后，所有设备需重新登录。':reset?'请联系邀请人或管理员，核验身份后获取30分钟内有效的重置码。':'使用邀请人提供的邀请码注册。资料填写、机会反馈与共创实验均由你自主选择。'}</p><form id="access-form" class="mt20">${inputs}${password}${confirm}${!security&&!reset?`<div class="access-notice mt16"><strong>体验与数据说明</strong><p class="small mt8">账号用于登录和保存你主动填写的偏好、收藏及反馈。你可以在“数据与隐私”导出或清除个人记录；加入共创实验需另外同意。机会信息和资格提示请以官方公告为准。</p></div><label class="access-consent mt16"><input name="accepted" type="checkbox" required>我已阅读并理解以上体验与数据说明</label>`:''}<button type="submit" class="btn primary wide mt20">${security?'修改密码并退出':reset?'重置密码':'注册并开始体验'}</button></form><a class="back-link" href="${security?'/app/me':'/login'}" data-nav>${security?'返回我的':'返回登录'}</a></div></main>`,after:()=>bind('#access-form','submit',async(_,f)=>{
  const data=checkedPassword(Object.fromEntries(new FormData(f)));
  if(security){await api('/api/auth/change-password',{method:'POST',data:{old_password:data.old_password,new_password:data.password}});state.user=null;state.csrf='';go('/login');toast('密码已修改，请重新登录');}
  else if(reset){await api('/api/auth/reset-password',{method:'POST',data});state.user=null;state.csrf='';go('/login');toast('密码已重置，请重新登录');}
  else{data.accepted=data.accepted==='on';const r=await api('/api/auth/register',{method:'POST',data});state.user=r;state.csrf=r.csrf;go('/app/profile');}
 })};
}

const roles={user:'普通用户',reviewer:'审核员',operator:'维护员'};
const roleDescriptions={user:'浏览机会、收藏行动并提交反馈',reviewer:'审核内容，管理正式收录与撤回',operator:'全部审核权限，以及采集、邀请码和账号管理'};
const reason=field('操作原因','reason','required maxlength="500" placeholder="简要说明本次调整，勿填写密码或邀请码"');
export async function renderAccessManage(path,params){
 if(!has('operator'))throw Object.assign(new Error('仅维护员可管理账号'),{status:403});
 const offset=Math.max(0,Number(params.get('offset'))||0),q=params.get('q')||'';
 const tabs=`<nav class="row gap12 wrap mb16" aria-label="账号管理"><a class="btn" href="/manage/invitations" data-nav>邀请码</a><a class="btn" href="/manage/users" data-nav>用户管理</a><a class="btn" href="/manage/access-audit" data-nav>账号操作记录</a></nav>`;
 if(path==='/manage/invitations'){
  const r=await api('/api/admin/invitations?offset='+offset);
  return {body:tabs+`<div class="work-title"><div><h1>邀请码</h1><p>4位数字邀请码，默认一人一码、7天有效。撤销不影响已注册账号。</p></div></div><form id="invite-form" class="manage-panel"><div class="row gap16 wrap">${field('批次 / 用途','label','required maxlength="120" placeholder="例如：九月首批体验"')}${field('生成数量','count','type="number" required min="1" max="50" value="1"')}${field('每码名额','max_uses','type="number" required min="1" max="1000" value="1"')}${field('有效天数','expires_days','type="number" required min="1" max="90" value="7"')}</div><button class="btn primary" type="submit">生成邀请码</button>${!state.site.registration?'<p class="note warning mt12">注册总开关当前关闭，邀请码暂不能兑换；需宿主启用注册。</p>':''}</form><section id="access-secret" class="manage-panel mt16" hidden></section><div class="work-table-wrap mt20"><table class="work-table access-table"><thead><tr><th>批次</th><th>已用 / 名额</th><th>有效期</th><th>状态</th><th>操作</th></tr></thead><tbody>${r.items.map(i=>`<tr><td>${e(i.label)}<span class="meta">${e(i.id)}</span></td><td>${i.used_count} / ${i.max_uses}</td><td>${e(time(i.expires_at))}</td><td>${e({ACTIVE:'可使用',REVOKED:'已撤销',EXPIRED:'已过期',EXHAUSTED:'已用完'}[i.status])}</td><td>${i.status==='ACTIVE'?`<button class="btn revoke-invite" data-id="${e(i.id)}">撤销</button>`:'—'}</td></tr>`).join('')}</tbody></table>${!r.total?'<p class="muted mt16">尚未创建邀请码。</p>':''}</div>${pagination(offset,r.total,30,n=>path+'?offset='+n)}`,after:()=>{
   bind('#invite-form','submit',async(_,f)=>{const data=Object.fromEntries(new FormData(f));for(const k of ['count','max_uses','expires_days'])data[k]=Number(data[k]);const result=await api('/api/admin/invitations',{method:'POST',data});secretBox(result.items.map(i=>`${i.code}  |  ${i.label}  |  名额 ${i.max_uses}  |  到期 ${time(i.expires_at)}`).join('\n'));toast('已生成。保存后切换标签可刷新列表');});
   bind('.revoke-invite','click',(_,b)=>modal('撤销邀请码','<p>该码将不能再用于注册，已注册账号不受影响。</p>',async()=>{await api('/api/admin/invitations/'+b.dataset.id+'/revoke',{method:'POST'});go(path);},'确认撤销',true));
  }};
 }
 if(path==='/manage/users'){
  const r=await api('/api/admin/users?offset='+offset+'&q='+encodeURIComponent(q));
  return {body:tabs+`<div class="work-title"><div><h1>用户管理</h1><p>维护员统一管理邀请码与账号，并拥有全部审核权限。</p></div></div><form id="user-search" class="row gap12 mb16"><input name="q" maxlength="80" value="${e(q)}" aria-label="搜索账号" placeholder="搜索账号"><button type="submit" class="btn">搜索</button></form><section id="access-secret" class="manage-panel" hidden></section><div class="work-table-wrap"><table class="work-table access-table"><thead><tr><th>账号</th><th>角色 / 状态</th><th>来源批次</th><th>操作</th></tr></thead><tbody>${r.items.map(u=>`<tr><td><strong>${e(u.username)}</strong><span class="meta">${e(time(u.created_at))}</span></td><td>${u.roles.map(x=>e(roles[x]||x)).join('、')}<span class="meta">${u.active?'正常':'已停用'}</span></td><td>${e(u.cohort)}</td><td><div class="row gap8 wrap">${u.username!==state.user.username?`<button class="btn edit-user" data-id="${e(u.id)}">角色与状态</button><button class="btn reset-user" data-id="${e(u.id)}" ${!u.active?'disabled':''}>重置密码</button>`:'当前账号'}<button class="btn revoke-user" data-id="${e(u.id)}">退出全部会话</button></div></td></tr>`).join('')}</tbody></table>${!r.total?'<p class="muted mt16">没有匹配账号。</p>':''}</div>${pagination(offset,r.total,30,n=>path+'?offset='+n+'&q='+encodeURIComponent(q))}`,after:()=>{
   bind('#user-search','submit',(_,f)=>go(path+'?q='+encodeURIComponent(new FormData(f).get('q'))));
   bind('.edit-user','click',(_,b)=>{
    const u=r.items.find(x=>x.id===b.dataset.id);
    modal('管理账号',`<div class="access-account-form"><div class="access-account-heading"><span class="avatar">${e(u.username.slice(0,1).toUpperCase())}</span><div><strong>${e(u.username)}</strong><p>设置登录状态与使用权限</p></div></div><label class="access-toggle"><input name="active" type="checkbox" ${u.active?'checked':''}><span><strong>允许登录</strong><small>关闭后，该账号将退出所有设备</small></span></label><fieldset class="access-role-fieldset"><legend>角色权限 <span>至少选择一项</span></legend><div class="access-role-options">${Object.entries(roles).map(([key,label])=>`<label class="access-role-card"><input type="checkbox" name="roles" value="${key}" ${u.roles.includes(key)?'checked':''}><span><strong>${label}</strong><small>${roleDescriptions[key]}</small></span></label>`).join('')}</div></fieldset>${reason}<p class="access-change-note">保存后，该用户需要重新登录。</p></div>`,async fd=>{
      const selected=fd.getAll('roles');if(!selected.length)throw new Error('请至少选择一种角色');
      await api('/api/admin/users/'+u.id,{method:'PATCH',data:{active:fd.has('active'),roles:selected,reason:fd.get('reason')}});go(path);
    },'保存更改');
   });
   bind('.reset-user','click',(_,b)=>modal('签发密码重置码','<p>请先在线下核验用户身份。重置码30分钟有效且仅能使用一次；新码会替换此前重置码。</p>'+reason,async fd=>{const result=await api('/api/admin/users/'+b.dataset.id+'/password-reset',{method:'POST',data:{reason:fd.get('reason')}});secretBox(result.code+'\n到期：'+time(result.expires_at)+'\n用户访问 /reset-password 输入重置码。');},'已核验身份，签发'));
   bind('.revoke-user','click',(_,b)=>modal('退出全部会话',reason,async fd=>{await api('/api/admin/users/'+b.dataset.id+'/revoke-sessions',{method:'POST',data:{reason:fd.get('reason')}});toast('会话已撤销');go(path);},'确认退出',true));
  }};
 }
 const r=await api('/api/admin/audit?offset='+offset);
 return {body:tabs+`<h1>账号操作记录</h1><div class="work-table-wrap mt20"><table class="work-table access-table"><thead><tr><th>操作</th><th>操作者</th><th>对象 / 说明</th><th>时间</th></tr></thead><tbody>${r.items.map(x=>`<tr><td>${e(x.action)}</td><td>${e(x.actor)}</td><td>${e(x.summary)}<span class="meta">${e(x.target)}</span></td><td>${e(time(x.created_at))}</td></tr>`).join('')}</tbody></table></div><nav class="pagination">${offset?`<a class="btn" data-nav href="${path}?offset=${Math.max(0,offset-30)}">上一页</a>`:''}${r.items.length===30?`<a class="btn" data-nav href="${path}?offset=${offset+30}">下一页</a>`:''}</nav>`,after:()=>{}};
}
