'use strict';
(() => {
const $=(q,root=document)=>root.querySelector(q), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=c=>c==null?'按需报价':new Intl.NumberFormat('zh-CN',{style:'currency',currency:'CNY'}).format(c/100);
const date=v=>v?new Date(v).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'—';
const uuid=()=>crypto.randomUUID();
const labels={DRAFT:'草稿',PUBLISHED:'已上架',ARCHIVED:'已下架',PENDING:'待确认',REQUESTED:'等待定制评估',QUOTED:'等待你确认报价',FULFILLED_TRIAL:'已安排试用',FULFILLED_MANUAL:'已人工核对开通',CANCELLED:'已取消',ACTIVE:'服务中',SCHEDULED:'下一服务期',EXPIRED:'已到期',REVOKED:'已撤销',APPROVED:'线索通过',REJECTED:'未采纳',NEEDS_INFO:'等待补充',QUEUED:'等待执行',DISPATCHING:'正在交接任务',RETRYABLE:'待核查 / 可重试',CORE_QUEUED:'已进入采集队列',CORE_RUNNING:'正在采集',RESULT_PENDING_REVIEW:'已有结果 · 等待整体审核',FAILED:'采集失败',BLOCKED:'服务或权限已阻止',NEEDS_RECOVERY:'等待恢复',CORE_STATUS_UNKNOWN:'采集状态需核查'};
const badge=(s,color='')=>`<span class="tag ${color}">${esc(labels[s]||s)}</span>`;
let user=null,csrf='',info={},pageEpoch=0,nextAction=0,modalBusy=false,toastTimer;
const actions=new Map();
function btn(text,fn,cls='secondary',extra=''){const id=String(++nextAction);actions.set(id,fn);return `<button class="btn ${cls}" data-run="${id}" ${extra}>${esc(text)}</button>`;}
function toast(text){const n=$('#toast');n.textContent=text;n.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>n.hidden=true,5000);}
async function request(path,{method='GET',body}={}){
 const options={method,credentials:'same-origin',cache:'no-store',headers:{}};
 if(body!==undefined){options.body=JSON.stringify(body);options.headers['Content-Type']='application/json';}
 if(method!=='GET')options.headers['X-CSRF-Token']=csrf;
 let r;try{r=await fetch(path,options);}catch(e){throw new Error('网络未返回确认。请保留此窗口并重试；同一次提交不会重复开通。');}
 let data;try{data=await r.json();}catch(e){throw new Error('服务返回格式异常，请刷新核对结果后再操作。');}
 if(!r.ok){const error=new Error(data.message|| (r.status===422?'请核对表单填写与数值范围':`请求未完成（${r.status}）`));error.status=r.status;throw error;}
 return data;
}
const api=(path,method='GET',body)=>request('/api/membership/'+path,{method,body});
const isOp=()=>user?.roles?.includes('operator'), isReviewer=()=>isOp()||user?.roles?.includes('reviewer');
const section=(title,subtitle='',action='')=>`<div class="section-head"><div><p class="eyebrow">DEEPAHA / OPPORTUNITY SERVICE</p><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div>${action}</div>`;
const empty=(title,text,action='')=>`<div class="empty"><strong>${esc(title)}</strong><p>${esc(text)}</p>${action}</div>`;
function field(name,label,value='',type='text',extra='',help=''){
 const full=type==='textarea'?' full':'';let control;
 if(type==='textarea')control=`<textarea name="${name}" ${extra}>${esc(value)}</textarea>`;
 else control=`<input name="${name}" type="${type}" value="${esc(value)}" ${extra}>`;
 return `<label class="field${full}">${esc(label)}${control}${help?`<small>${esc(help)}</small>`:''}</label>`;
}
function select(name,label,options,value){return `<label class="field">${esc(label)}<select name="${name}">${options.map(([k,v])=>`<option value="${esc(k)}" ${k===value?'selected':''}>${esc(v)}</option>`).join('')}</select></label>`;}
const check=(name,text,checked=false,value='on')=>`<label class="check"><input type="checkbox" name="${name}" value="${esc(value)}" ${checked?'checked':''}><span>${esc(text)}</span></label>`;
function formDialog(title,html,submit,submitLabel='确认保存'){
 $('#modal-title').textContent=title;
 $('#modal-body').innerHTML=`<form id="dialog-form"><div class="form-grid">${html}</div><p class="form-error" role="alert"></p><div class="form-actions"><button class="btn" type="submit">${esc(submitLabel)}</button></div></form>`;
 const form=$('#dialog-form'),key=uuid();
 form.addEventListener('submit',async e=>{
  e.preventDefault();if(modalBusy)return;modalBusy=true;const button=$('button[type=submit]',form);button.disabled=true;$('.form-error',form).textContent='';
  try{await submit(new FormData(form),key);modalBusy=false;$('#modal').close();toast('操作已保存');await render();}
  catch(err){$('.form-error',form).textContent=err.message;modalBusy=false;button.disabled=false;}
 });
 $('#modal').showModal();setTimeout(()=>$('input:not([type=hidden]),select,textarea',form)?.focus(),0);
}
function nav(){
 const current=location.hash.slice(1)||'services';
 const primary=[['services','◈','服务方案'],['watches','◎','我的跟踪'],['feedback','＋','网站建议'],['account','○','我的订阅']];
 const navItem=([id,glyph,label])=>`<a href="#${id}" class="${current===id?'active':''}" ${current===id?'aria-current="page"':''}><span class="nav-glyph" aria-hidden="true">${glyph}</span>${label}</a>`;
 $('#primary-nav').innerHTML=primary.map(navItem).join('')+navItem(['notices','◷','更新消息'])+(isReviewer()?'<div class="nav-separator"></div>'+navItem(['review','▤','网站线索审核']):'')+(isOp()?navItem(['manage','⚙','服务管理']):'');
 $('#mobile-nav').innerHTML=primary.map(navItem).join('');
 $('#session-actions').innerHTML=btn('消息',()=>go('notices'),'subtle small')+(user?btn(user.username+' · 退出',logout,'secondary small'):btn('登录',()=>go('login'),'small'));
 $('#demo-notice').hidden=!info.demo;$('#backlink').hidden=!!info.demo;
 const names={services:'个人服务',watches:'持续跟踪',feedback:'共建机会来源',account:'服务与申请',notices:'更新消息',review:'网站线索审核',manage:'服务管理',login:'登录'};
 $('#crumb').textContent=names[current.split('-')[0]]||'服务管理';
}
function go(page){if(location.hash==='#'+page)render();else location.hash=page;}
async function logout(){await request('/api/auth/logout',{method:'POST',body:{}});user=null;csrf='';$('#modal').close();$('#modal-body').replaceChildren();actions.clear();go('services');}
function loginView(){
 return section('欢迎回来','使用机会星图账号，继续管理你的服务与跟踪。')+`<section class="card auth-card"><h2>登录服务中心</h2><form id="login-form"><div class="form-grid">${field('username','账号','','text','required autocomplete="username" maxlength="80"')}${field('password','密码','','password','required autocomplete="current-password" maxlength="256"')}</div><p class="form-error" role="alert"></p><div class="form-actions"><button class="btn" type="submit">登录</button></div></form>${info.demo?'<p class="muted small">本地演示账号及随机密码见启动终端或 LOCAL_DEMO_ACCOUNTS.txt。维护员账号为 maintainer。</p>':''}</section>`;
}
async function servicesView(){
 const plans=await api('plans');
 let h=`<div class="hero"><div><p class="eyebrow">LESS SEARCHING. MORE POSSIBILITY.</p><h1>重要的机会，<br>值得被持续关注。</h1><p>短期集中寻找、全年持续留意，或围绕指定网站跟踪。选择与你当下目标相符的服务。</p></div><div class="orb" aria-hidden="true">↗</div></div>`;
 h+=plans.length?'<div class="grid plans">'+plans.map(p=>{
  const t=p.terms;return `<article class="card plan-card ${t.tier==='DEEP'?'featured':''}"><div class="row between"><h2>${esc(t.name)}</h2>${badge(t.tier==='CUSTOM'?'先评估，后确认':`${t.months}个自然月`,t.tier==='CUSTOM'?'orange':'')}</div><p class="description">${esc(t.description)}</p><div class="price">${money(t.price_cents)}${t.price_cents!=null?'<small> / 期</small>':''}</div><div class="plan-points"><div class="point"><b>✓</b><span>${t.topic_limit}个同时启用的跟踪主题</span></div><div class="point"><b>✓</b><span>已发布机会检查间隔 ${t.scan_hours} 小时</span></div><div class="point"><b>✓</b><span>${t.site_limit?`${t.site_limit}个公开网站名额，先审核接入；网站调查目标 ${t.site_scan_hours} 小时`:'站内记录新发现与内容变化'}</span></div>${t.services.filter(s=>s.capability==='manual').map(s=>`<div class="point"><b>✓</b><span>${esc(s.label)} · 人工履约</span></div>`).join('')}</div>${btn(t.tier==='CUSTOM'?'提交定制需求':'申请 '+t.name,()=>orderDialog(p),t.tier==='DEEP'?'':'secondary')}</article>`;
 }).join('')+'</div>':empty('服务方案正在准备中','公开机会和原有免费功能不受影响。套餐经维护员确认后才会上架。',isOp()?btn('管理并上架套餐',()=>go('manage')):'');
 h+='<div class="info-strip"><b>免费始终可用</b><span>机会总览、公开依据、原有收藏和截止提醒不因订阅到期而消失。新增订阅只承担持续跟踪服务，不改变资格判断。</span></div><p class="muted small">一次申请对应一个固定服务期，不自动续费。续购或换档在现有服务期结束后接续；当前不提供自动支付或自动退款。</p>';
 return h;
}
function orderDialog(p){
 if(!user){go('login');return;}
 const t=p.terms;
 formDialog(t.tier==='CUSTOM'?'告诉我们，你想持续关注什么':'确认服务申请',`<div class="field full"><div class="info-strip">${esc(t.name)} · ${t.months}个自然月 · ${money(t.price_cents)}<br>主题 ${t.topic_limit} 个；${t.site_limit?`网站 ${t.site_limit} 个；`:''}目标间隔 ${t.scan_hours} 小时。已存在服务时从下一服务期生效。</div></div>${field('note',t.tier==='CUSTOM'?'关注目标与公开网站':'补充说明（可选）','','textarea',`${t.tier==='CUSTOM'?'required minlength="5"':''} maxlength="3000"`,t.tier==='CUSTOM'?'请勿提供密码、Cookie或私密链接。网站建议可先在“网站建议”单独提交审核。':'此操作仅创建服务申请，不代表付款成功。')}<div class="field full">${check('accepted','已核对范围、周期与价格，了解无自动续费及结果保证。')}</div>`,async(d,key)=>{
  if(!d.has('accepted'))throw new Error('请先确认服务范围与说明。');
  await api('orders','POST',{code:p.code,version:p.version,key,note:d.get('note')||''});
 },t.tier==='CUSTOM'?'提交评估申请':'创建服务申请');
}
async function accountView(){
 const [me,orders]=await Promise.all([api('me'),api('orders')]);const e=me.entitlements;
 let h=section('我的订阅','服务周期、待确认报价与历史申请，集中在这里查看。',isReviewer()?btn(isOp()?'进入服务管理':'进入线索审核',()=>go(isOp()?'manage':'review')):'');
 h+=`<div class="hero"><div><p class="eyebrow">YOUR CURRENT SERVICE</p><h2>${esc(e.name)}</h2><p>${e.ends_at?'当前服务结束：'+date(e.ends_at)+'（北京时间）':'尚未开通持续跟踪服务。公开机会仍可正常查看。'}</p></div>${badge(e.tier==='FREE'?'免费使用':'服务中','orange')}</div>`;
 h+='<h2 class="section-label">服务周期</h2>'+(me.grants.length?'<div class="stack">'+me.grants.map(g=>`<div class="card list-card"><div><h3>${esc(g.terms.name)}</h3><p class="details">${date(g.starts_at)} → ${date(g.ends_at)}</p><p class="muted small">${g.method==='TRIAL'?'试用赠送 · 不代表收款':'维护员已人工核对外部付款'}</p></div>${badge(g.status,g.status==='ACTIVE'?'green':'gray')}</div>`).join('')+'</div>':empty('当前没有服务周期','申请后需由维护员完成服务确认。'));
 h+='<h2 class="section-label">服务申请</h2>'+(orders.length?'<div class="stack">'+orders.map(o=>orderCard(o,false)).join('')+'</div>':empty('还没有服务申请','先了解服务，再决定需要多长时间的陪伴。',btn('查看服务方案',()=>go('services'))));
 return h;
}
function orderCard(o,manage){
 let controls='';
 if(!manage&&o.state==='QUOTED')controls+=btn('查看并确认报价',()=>formDialog('确认定制报价',`<div class="field full"><div class="info-strip">${money(o.amount_cents)} / ${o.terms.months}个自然月<br>主题 ${o.terms.topic_limit} 个 · 网站 ${o.terms.site_limit} 个<br>报价有效至 ${date(o.quote_expires)}</div><p class="note-block">${esc(o.terms.scope)}</p>${check('agree','我已确认以上定制范围、周期及报价。')}</div>`,async(d,key)=>{if(!d.has('agree'))throw new Error('请确认定制方案');await api(`orders/${o.id}/accept`,'POST',{version:o.version,key});},'确认方案'));
 if(!manage&&['PENDING','REQUESTED','QUOTED'].includes(o.state))controls+=btn('取消申请',()=>formDialog('取消服务申请','<p class="field full">只取消此条待处理申请，不影响已有服务。</p>',async(d,key)=>api(`orders/${o.id}/cancel`,'POST',{version:o.version,key}),'确认取消'),'subtle small');
 if(manage&&['REQUESTED','QUOTED'].includes(o.state))controls+=btn('制定报价',()=>quoteDialog(o));
 if(manage&&o.state==='PENDING'){controls+=btn('人工核对开通',()=>confirmDialog(o,'MANUAL'));controls+=btn('赠送试用',()=>confirmDialog(o,'TRIAL'),'orange small');}
 return `<article class="card list-card"><div class="grow"><div class="row"><h3>${esc(o.terms.name)}</h3>${badge(o.state)}</div><p class="details">${manage?'用户 '+esc(o.owner)+' · ':''}${money(o.amount_cents)} · ${o.terms.months}个自然月 · ${date(o.created_at)}</p>${o.note?`<p class="note-block">${esc(o.note)}</p>`:''}${o.terms.scope?`<p class="note-block">定制范围：${esc(o.terms.scope)}</p>`:''}${controls?`<div class="row">${controls}</div>`:''}</div><span class="muted small">#${o.id.slice(0,8)}</span></article>`;
}
function quoteDialog(o){formDialog('定制服务报价',field('amount','总价（元）',o.amount_cents==null?'':(o.amount_cents/100).toFixed(2),'text','required inputmode="decimal"')+field('months','自然月数',o.terms.months,'number','required min="1" max="36"')+field('site_limit','同时跟踪网站',o.terms.site_limit||3,'number','required min="1" max="20"')+field('topic_limit','同时跟踪主题',o.terms.topic_limit,'number','required min="0" max="50"')+field('scope','明确的履约范围',o.terms.scope||'','textarea','required minlength="10" maxlength="3000"','先核验来源是否可处理，不承诺绕过登录、反爬或保证机会结果。'),async(d,key)=>api(`manage/orders/${o.id}/quote`,'POST',{version:o.version,key,amount_cents:cents(d.get('amount')),months:Number(d.get('months')),site_limit:Number(d.get('site_limit')),topic_limit:Number(d.get('topic_limit')),scope:d.get('scope')}),'发送报价');}
function confirmDialog(o,method){
 const manual=method==='MANUAL';
 formDialog(manual?'人工核对外部付款':'赠送试用服务',`<div class="field full"><div class="info-strip orange">用户 ${esc(o.owner)} · ${esc(o.terms.name)}<br>${manual?'此处不连接支付机构。请先从商户后台核对真实到账，不接受用户自称付款。':'这是试用赠送，不记作收款；服务周期按订单条款安排。'}</div></div>`+(manual?field('amount','实际核对金额（元）',(o.amount_cents/100).toFixed(2),'text','required inputmode="decimal"')+field('reference','唯一外部收款核对凭据','','text','required minlength="5" maxlength="128"'):'')+field('reason','开通原因 / 核对记录','','textarea','required minlength="5" maxlength="1000"')+`<div class="field full">${check('confirm','我确认本次操作已获授权，且已核对服务对象与条款。')}</div>`,async(d,key)=>{if(!d.has('confirm'))throw new Error('请确认本次开通授权');await api(`manage/orders/${o.id}/confirm`,'POST',{version:o.version,key,method,amount_cents:manual?cents(d.get('amount')):0,reference:manual?d.get('reference'):'',reason:d.get('reason')});},manual?'确认核对并开通':'确认赠送试用');
}
function cents(value){const s=String(value).trim();if(!/^\d{1,6}(\.\d{1,2})?$/.test(s))throw new Error('金额请填写正数，最多两位小数');const [a,b='']=s.split('.');return Number(a)*100+Number(b.padEnd(2,'0'));}
async function feedbackView(){
 const mine=await api('submissions');
 let h=section('一起补全机会来源','你发现的一个公开网站，可能帮助更多人看见原本错过的机会。',btn('＋ 提交网站',submitDialog,''));
 h+='<div class="info-strip"><b>提交 → 线索审核 → 来源接入 → 机会审核</b><span>审核网站与发布机会是两件事。网站线索通过，不代表其中每条内容已核实。</span></div>';
 h+=mine.length?'<div class="stack">'+mine.map(s=>`<article class="card"><div class="row between"><h3>${esc(s.lead.name)}</h3>${badge(s.lead.state,s.lead.state==='APPROVED'?'green':'')}</div><p class="url-line">${esc(s.lead.url)}</p><p class="note-block">${esc(s.note||'未填写额外说明')}</p>${s.lead.decision_note?`<p class="details small">审核回复：${esc(s.lead.decision_note)}</p>`:''}<div class="row">${s.lead.state==='NEEDS_INFO'?btn('补充说明',()=>formDialog('补充网站信息',field('note','补充说明',s.note,'textarea','required minlength="5" maxlength="2000"'),async(d,key)=>api(`submissions/${s.id}/supplement`,'POST',{version:s.lead.version,key,note:d.get('note')}))):''}${s.lead.state==='APPROVED'?btn('加入定制跟踪',async()=>{await api('watches/sites','POST',{submission_id:s.id,key:uuid()});toast('已加入，等待维护员接入与授权');go('watches');}):''}</div></article>`).join('')+'</div>':empty('还没有提交网站','免费用户也能提交。我们会保留处理进度，而不是让建议石沉大海。');
 return h;
}
function submitDialog(){formDialog('提交一个公开机会网站',field('name','网站 / 栏目名称','','text','required maxlength="200"')+select('kind','提交用途',[['SOURCE','补充公共来源'],['CUSTOM','我的定制跟踪需求']],'SOURCE')+`<div class="field full">${field('url','公开网址','','url','required maxlength="2048" placeholder="https://…"')}</div>`+field('note','你希望发现什么机会？','','textarea','maxlength="2000"')+`<div class="field full">${check('consent','我确认这是无需提供登录凭据的公开网址，同意平台核验后用于公共来源建设。我的身份与个人需求不公开。')}</div>`,async(d,key)=>api('submissions','POST',{name:d.get('name'),url:d.get('url'),kind:d.get('kind'),note:d.get('note'),consent:d.has('consent'),key}),'提交审核');}
async function watchesView(){
 const [me,ws,js]=await Promise.all([api('me'),api('watches'),api('jobs')]);const e=me.entitlements;
 let h=section('我的持续跟踪','让关注变成可回看的记录，而不是反复打开同一个网页。',btn('＋ 添加跟踪主题',topicDialog,''));
 h+=`<div class="stat-grid"><div class="stat"><span class="muted small">主题名额</span><b>${ws.filter(w=>w.kind==='TOPIC'&&w.effective).length} / ${e.topic_limit}</b></div><div class="stat"><span class="muted small">定制网站名额</span><b>${ws.filter(w=>w.kind==='SITE'&&w.effective).length} / ${e.site_limit}</b></div><div class="stat"><span class="muted small">已发布机会检查</span><b>${e.tier==='FREE'?'未开通':e.scan_hours+' 小时'}</b></div></div>`;
 h+='<div class="info-strip"><span>主题跟踪检查已发布机会；指定网站需维护员接入采集。目标间隔不代表检查必定完成，以下显示实际检查时间。</span></div>';
 h+=ws.length?'<div class="stack">'+ws.map(w=>{const j=js.find(j=>j.watch_id===w.id);return `<article class="card"><div class="row between"><h3>${esc(w.config.name)}</h3>${badge(!w.enabled?'已暂停':!w.effective?'权益未生效 / 名额外':w.kind==='SITE'?(j?.state||'待维护员接入'):'跟踪已启用',w.effective?'green':'gray')}</div><p class="details small muted">${w.kind==='SITE'?esc(w.config.url):[w.config.q,w.config.kind,w.config.region].filter(Boolean).map(esc).join(' · ')}</p><p class="small muted">${w.kind==='SITE'?'最近任务交接':'最近完整检查'}：${date(w.last_checked)}</p>${w.last_error?`<p class="note-block">本轮未完成：${esc(w.last_error)}</p>`:''}<div class="row">${btn(w.enabled?'暂停跟踪':'重新启用',async()=>{await api(`watches/${w.id}/toggle`,'POST',{version:w.version,enabled:!w.enabled,key:uuid()});await render();},'subtle small')}</div></article>`;}).join('')+'</div>':empty('从一个你关心的方向开始','例如“广告实习 + 宁波”。指定网站请先在网站建议中提交审核。',btn('提交指定网站',()=>go('feedback')));
 return h;
}
function topicDialog(){formDialog('新增机会跟踪主题',field('name','给主题起个名字','','text','required maxlength="100"')+field('q','关键词','','text','maxlength="200" placeholder="例如：品牌、实习、校招"')+field('kind','类别（可选）','','text','maxlength="100"')+field('region','地区（可选）','','text','maxlength="100" placeholder="例如：宁波"'),async(d,key)=>api('watches/topics','POST',{name:d.get('name'),q:d.get('q'),kind:d.get('kind'),region:d.get('region'),key}),'保存主题');}
async function noticesView(){const ns=await api('notices');return section('更新消息','只保留值得你回来看一眼的进展。')+(ns.length?'<div class="stack">'+ns.map(n=>`<article class="card ${n.read_at?'':'unread'}"><div class="row between"><h3>${esc(n.title)}</h3><span class="muted small">${date(n.created_at)}</span></div><p class="note-block">${esc(n.body)}</p><div class="row">${!n.read_at?btn('标为已读',async()=>{await api(`notices/${n.id}/read`,'POST',{});await render();},'subtle small'):badge('已读','gray')}</div></article>`).join('')+'</div>':empty('暂时没有新消息','订阅、审核和跟踪的进展会汇总在这里。'));}
async function reviewView(){
 const ls=await api('review/leads');
 return section('网站线索审核','整体判断是否值得接入，不将线索审核等同于机会事实审核。',!info.demo?'<a class="btn secondary" href="/review">原机会审核 ↗</a>':'')+`<p class="muted small">按最新提交展示，最多200条。请勿在发给用户的回复或公开采集说明中包含个人隐私。</p><div class="stack section-label">`+(ls.length?ls.map(l=>{
  let controls='';if(['PENDING','NEEDS_INFO'].includes(l.state))controls=btn('处理线索',()=>reviewDialog(l));
  if(isOp()&&l.state==='APPROVED'){controls+=btn(l.source_id?'重新核对来源登记':'登记到原来源管理',async()=>{const s=await api(`manage/leads/${l.id}/adopt`,'POST',{});toast('来源已登记；启用状态未自动改变');await render();},'secondary small');if(l.source_id)controls+=btn('明确启用此来源',()=>formDialog('启用已审核来源',`<p class="field full">将允许既有采集系统为此来源接受任务。此动作本身不创建采集任务。</p><div class="field full">${check('agree','已确认公开来源、允许范围和成本安排。')}</div>`,async(d)=>{if(!d.has('agree'))throw new Error('请确认启用范围');await api(`manage/leads/${l.id}/enable`,'POST',{});},'启用来源'),'orange small');}
  return `<article class="card"><div class="row between"><h3>${esc(l.name)}</h3>${badge(l.state)}</div><p class="url-line">${esc(l.url)}</p><p class="small muted">${l.submissions.length}位用户提交 · ${l.source_id?'已关联来源 '+esc(l.source_id):'未登记采集来源'}</p>${l.submissions.map(s=>`<p class="note-block">${esc(s.owner)}：${esc(s.note)}</p>`).join('')}${l.decision_note?`<p class="small muted">回复：${esc(l.decision_note)}</p>`:''}<div class="row">${controls}</div></article>`;
 }).join(''):empty('暂无线索待处理','用户提交的公开网站会自动进入此处。'))+'</div>';
}
function reviewDialog(l){formDialog('整体审核网站线索',select('decision','处理结果',[['APPROVE','通过线索'],['NEEDS_INFO','退回补充'],['REJECT','不采纳']],'APPROVE')+select('tier','核验后的来源类型',[['COMMUNITY_SIGNAL','社区 / 用户线索'],['OFFICIAL_PRIMARY','已核验官方一手来源'],['OFFICIAL_AGGREGATOR','已核验官方汇总来源'],['TRUSTED_SECONDARY','可信二手来源']],'COMMUNITY_SIGNAL')+field('approved_url','核验后的公开地址',l.url,'url','maxlength="2048"')+field('note','发给用户的审核回复','','textarea','required minlength="2" maxlength="1000"')+field('public_brief','审核后的公开采集说明','','textarea','maxlength="3000"','仅通过时必填，至少10字。不要复制用户的私人需求、身份或网页中诱导执行的指令。'),async(d,key)=>api(`review/leads/${l.id}/decision`,'POST',{version:l.version,key,decision:d.get('decision'),tier:d.get('tier'),approved_url:d.get('approved_url'),note:d.get('note'),public_brief:d.get('public_brief')}),'保存审核结论');}
const managerTabs=[['manage','套餐价格'],['manage-services','服务项目'],['manage-orders','申请与报价'],['manage-grants','用户权益'],['manage-jobs','跟踪任务'],['manage-audit','操作记录']];
function managerNav(route){return '<nav class="subnav" aria-label="服务管理分类">'+managerTabs.map(([r,t])=>`<a href="#${r}" class="${r===route?'active':''}">${t}</a>`).join('')+'</nav>';}
async function manageView(route){
 let h=section('服务管理','套餐价格与服务项目由这里统一维护；新条款不追溯改变旧订单。')+managerNav(route);
 if(route==='manage'){
  const ps=await api('manage/plans');h+=`<div class="row between"><p class="muted small">所有预置价格均为试运营假设，默认草稿，维护员确认后再上架。</p>${btn('＋ 新建套餐',()=>planDialog(null),'')}</div><div class="stack section-label">`+ps.map(p=>`<article class="card"><div class="row between"><h3>${esc(p.terms.name)}</h3>${badge(p.status)}</div><p class="details">${money(p.terms.price_cents)} / ${p.terms.months}个自然月 · 主题 ${p.terms.topic_limit} · 网站 ${p.terms.site_limit}</p><p class="muted small">版本 ${p.version} · ${esc(p.code)} · 检查间隔 ${p.terms.scan_hours} 小时</p><div class="row">${btn('编辑新版本',()=>planDialog(p))}${btn(p.status==='PUBLISHED'?'下架':'确认上架',()=>formDialog(p.status==='PUBLISHED'?'下架套餐':'确认上架套餐',`<p class="field full">${esc(p.terms.name)} · ${money(p.terms.price_cents)}<br>${p.status==='PUBLISHED'?'不再接受新申请，已有订单和权益保持不变。':'请确认价格与实际交付能力一致；未接入的渠道不能承诺已发送。'}</p>`,async()=>api(`manage/plans/${p.code}/status`,'POST',{status:p.status==='PUBLISHED'?'ARCHIVED':'PUBLISHED',version:p.version}),'确认'),'subtle small')}</div></article>`).join('')+'</div>';
 }else if(route==='manage-services'){
  const ss=await api('manage/services');h+=btn('＋ 新建服务项目',()=>serviceDialog(null),'')+'<div class="stack section-label">'+ss.map(s=>`<article class="card list-card"><div><h3>${esc(s.label)}</h3><p class="details">${esc(s.description)}</p><p class="muted small">${esc(s.code)} · ${s.capability==='manual'?'人工履约':esc(s.capability)} · ${s.active?'启用':'停用'}</p></div>${btn('编辑项目',()=>serviceDialog(s),'secondary small')}</article>`).join('')+'</div>';
 }else if(route==='manage-orders'){
  const os=await api('manage/orders');h+='<p class="muted small">最多展示最近100条申请。人工核对不是在线支付验签；试用与收款分别记录。</p><div class="stack section-label">'+(os.length?os.map(o=>orderCard(o,true)).join(''):empty('暂无服务申请','用户申请后在这里处理。'))+'</div>';
 }else if(route==='manage-grants'){
  const gs=await api('manage/grants');h+='<div class="stack">'+(gs.length?gs.map(g=>`<article class="card"><div class="row between"><h3>${esc(g.owner)} · ${esc(g.terms.name)}</h3>${badge(g.status)}</div><p class="details">${date(g.starts_at)} → ${date(g.ends_at)}</p><p class="muted small">${g.method==='TRIAL'?'试用赠送':'人工核对外部付款'}</p><div class="row">${!g.revoked_at?btn('撤销权益',()=>formDialog('撤销权益，不自动退款',field('reason','撤销原因','','textarea','required minlength="5" maxlength="1000"')+'<p class="field full muted small">撤销后停止后续新服务。退款必须在支付或财务渠道另行处理。</p>',async(d,key)=>api(`manage/grants/${g.id}/revoke`,'POST',{reason:d.get('reason'),key}),'确认撤销'),'danger small'):''}</div></article>`).join(''):empty('暂无用户权益','维护员确认申请后生成。'))+'</div>';
 }else if(route==='manage-jobs'){
  const [ws,js]=await Promise.all([api('manage/watches'),api('manage/jobs')]);
  h+=`<div class="row">${btn('检查已发布主题机会',async()=>{const r=await api('manage/scan-topics','POST',{});toast(`检查 ${r.checked} 个主题；新增 ${r.notices_created} 条消息；未完成 ${r.failed} 个`);await render();},'')}${btn('检查已发布的网站机会',async()=>{const r=await api('manage/scan-site-publications','POST',{});toast(`检查 ${r.checked} 个网站；新增 ${r.notices_created} 条消息；未完成 ${r.failed} 个`);await render();})}${btn('网站线索与来源接入',()=>go('review'))}</div><div class="info-strip orange">网站任务交接可能触发原WMA费用。仅维护员明确授权后创建；保持原系统连接、队列和并发限制。</div>`;
  h+='<h2 class="section-label">指定网站跟踪</h2><div class="stack">'+ws.filter(w=>w.kind==='SITE').map(w=>`<div class="card"><div class="row between"><h3>${esc(w.owner)} · ${esc(w.config.name)}</h3>${badge(w.effective?'权益有效':'暂不执行',w.effective?'green':'gray')}</div><p class="url-line">${esc(w.config.url)}</p><div class="row">${btn('安排一轮检查',()=>formDialog('授权一次网站检查',field('connection','已登记执行连接','default','text','required pattern="[a-zA-Z0-9_-]{1,48}"')+`<div class="field full">${check('agree','已确认来源已审核并启用，理解本轮任务可能产生采集费用。')}</div>`,async(d,key)=>{if(!d.has('agree'))throw new Error('请先确认执行授权');await api(`manage/watches/${w.id}/prepare`,'POST',{connection:d.get('connection'),key});},'安排检查'))}</div></div>`).join('')+'</div>';
  h+='<h2 class="section-label">任务进展</h2><div class="stack">'+(js.length?js.map(j=>`<div class="card"><div class="row between"><h3>${esc(j.owner)} · #${j.id.slice(0,8)}</h3>${badge(j.state)}</div><p class="details small muted">授权维护员 ${esc(j.actor)} · 连接 ${esc(j.connection)} · 尝试 ${j.attempts} 次</p>${j.error?`<p class="note-block">${esc(j.error)}</p>`:''}<div class="row">${['QUEUED','RETRYABLE','DISPATCHING'].includes(j.state)?btn('交接原采集任务',async()=>{const r=await api(`manage/jobs/${j.id}/dispatch`,'POST',{});toast(labels[r.state]||r.state);await render();},'orange small'):''}${j.core_task_id?btn('查询采集状态',async()=>{await api(`manage/jobs/${j.id}/refresh`,'POST',{});await render();},'secondary small'):''}${info.demo&&j.core_task_id&&j.state==='CORE_QUEUED'?btn('模拟结果返回',async()=>{await api(`demo/jobs/${encodeURIComponent(j.core_task_id)}/complete`,'POST',{});await api(`manage/jobs/${j.id}/refresh`,'POST',{});await render();},'subtle small'):''}</div></div>`).join(''):empty('暂无采集任务','安排检查仅排队，点击交接后才会调用原采集接口。'))+'</div>';
 }else{
  const as=await api('manage/audit');h+='<div class="stack">'+as.map(a=>`<div class="card"><div class="row between"><strong>${esc(a.event)}</strong><span class="small muted">${date(a.created_at)}</span></div><p class="small muted">${esc(a.actor)} · ${esc(a.target)}</p><p class="note-block">${esc(JSON.stringify(a.data))}</p></div>`).join('')+'</div>';
 }
 return h;
}
async function planDialog(p){
 const ss=await api('manage/services');const t=p?.terms||{name:'',description:'',tier:'BASIC',months:2,price_cents:2990,topic_limit:3,site_limit:0,scan_hours:24,site_scan_hours:24,sort_order:40,service_codes:['topic_watch','inapp_alerts']};
 formDialog(p?'发布一版新的套餐条款':'新建套餐草稿',(!p?field('code','唯一套餐标识','','text','required pattern="[a-z][a-z0-9_]{1,47}"','使用小写字母、数字和下划线。'):'')+field('name','套餐名称',t.name,'text','required maxlength="80"')+select('tier','服务类型',[['BASIC','基础订阅'],['DEEP','深度订阅'],['CUSTOM','定制订阅']],t.tier)+field('description','一句话说明',t.description,'textarea','maxlength="1200"')+field('price','每期总价（元）',t.price_cents==null?'':(t.price_cents/100).toFixed(2),'text','inputmode="decimal"','定制订阅不使用固定价格，改由报价单确认。')+field('months','自然月数',t.months,'number','required min="1" max="36"')+field('topic_limit','同时启用主题',t.topic_limit,'number','required min="0" max="50"')+field('site_limit','同时跟踪网站',t.site_limit,'number','required min="0" max="20"')+field('scan_hours','目标检查间隔（小时）',t.scan_hours,'number','required min="6" max="168"')+field('site_scan_hours','网站调查间隔（小时）',t.site_scan_hours||24,'number','required min="24" max="720"','网站调查与低成本的已发布目录检查分别计时。')+field('sort_order','显示顺序',t.sort_order,'number','required min="0" max="999"')+`<div class="field full">包含服务<div class="checks">${ss.map(s=>check('service_codes',s.label+(s.active?'':'（停用，不能加入新版本）'),t.service_codes.includes(s.code),s.code)).join('')}</div></div>`,async(d)=>{
  const data={name:d.get('name'),description:d.get('description'),tier:d.get('tier'),months:Number(d.get('months')),price_cents:d.get('tier')==='CUSTOM'?null:cents(d.get('price')),topic_limit:Number(d.get('topic_limit')),site_limit:Number(d.get('site_limit')),scan_hours:Number(d.get('scan_hours')),site_scan_hours:Number(d.get('site_scan_hours')),sort_order:Number(d.get('sort_order')),service_codes:d.getAll('service_codes')};
  if(p)await api(`manage/plans/${p.code}`,'PUT',{version:p.version,data});else await api('manage/plans','POST',{code:d.get('code'),data});
 },p?'保存新版本':'保存草稿');
}
function serviceDialog(s){formDialog(s?'编辑服务项目':'新增服务项目',field('code','项目标识',s?.code||'','text',`required pattern="[a-z][a-z0-9_]{1,47}" ${s?'readonly':''}`)+field('label','服务名称',s?.label||'','text','required maxlength="80"')+select('capability','实际交付能力',[['manual','人工履约'],['topic_watch','主题跟踪'],['inapp_alerts','站内提醒'],['site_watch','指定网站跟踪']],s?.capability||'manual')+field('description','具体服务说明',s?.description||'','textarea','maxlength="1200"')+`<div class="field full">${check('active','允许加入新的套餐版本',s?.active??true)}</div>`,async(d)=>api('manage/services','POST',{version:s?.version??null,data:{code:d.get('code'),label:d.get('label'),description:d.get('description'),capability:d.get('capability'),active:d.has('active')}}));}
async function render(){
 const epoch=++pageEpoch,route=location.hash.slice(1)||'services';actions.clear();nav();$('#content').innerHTML='<p class="loading">正在读取…</p>';
 try{
  let html;
  if(route==='login'||(route!=='services'&&!user))html=loginView();
  else if(route.startsWith('manage')){if(!isOp())throw new Error('此区域仅对维护员开放');html=await manageView(route);}
  else if(route==='review'){if(!isReviewer())throw new Error('此区域仅对审核员或维护员开放');html=await reviewView();}
  else html=await ({services:servicesView,account:accountView,feedback:feedbackView,watches:watchesView,notices:noticesView}[route]||servicesView)();
  if(epoch!==pageEpoch)return;$('#content').innerHTML=html;nav();
  $('#login-form')?.addEventListener('submit',async e=>{
   e.preventDefault();const form=e.currentTarget,button=$('button[type=submit]',form);button.disabled=true;
   try{const d=new FormData(form);user=await request('/api/auth/login',{method:'POST',body:{username:d.get('username'),password:d.get('password')}});csrf=user.csrf;go(isOp()?'manage':isReviewer()?'review':'account');}
   catch(err){$('.form-error',form).textContent=err.message;button.disabled=false;}
  });
 }catch(err){if(epoch!==pageEpoch)return;$('#content').innerHTML=empty('暂时无法完成此操作',err.message,btn('重新读取',render));nav();}
}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-run]');if(!b||b.disabled)return;const fn=actions.get(b.dataset.run);if(!fn)return;b.disabled=true;try{await fn();}catch(err){toast(err.message);}finally{b.disabled=false;}});
$('#close-modal').addEventListener('click',()=>{if(!modalBusy)$('#modal').close();});
$('#modal').addEventListener('cancel',e=>{if(modalBusy)e.preventDefault();});
window.addEventListener('hashchange',()=>{if(!modalBusy)$('#modal').close();render();});
async function start(){try{info=await api('info');}catch(e){info={};}try{user=await request('/api/auth/me');csrf=user.csrf;}catch(e){user=null;}await render();}
start();
})();
