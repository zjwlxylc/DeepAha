export const state={user:null,csrf:'',site:{registration:false,public_catalog:false}};
export const $=(q,scope=document)=>scope.querySelector(q);
export const $$=(q,scope=document)=>[...scope.querySelectorAll(q)];
export const e=(v)=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const icon=(name,cls='')=>`<svg class="icon ${cls}" viewBox="0 0 24 24" aria-hidden="true">${window.DeepAhaIcons[name]||window.DeepAhaIcons.file}</svg>`;
export const brand=()=>`<a href="/" data-nav class="logo"><img class="brand-mark" src="/product/brand-logo.png" width="40" height="40" alt="DeepAha"><span><span class="logo-word">DeepAha</span><span class="brand-caption">机会星图</span></span></a>`;
export const has=(role)=>Boolean(state.user?.roles?.includes(role)||(role==='reviewer'&&state.user?.roles?.includes('operator')));
export const time=(s)=>{if(!s)return '—';const date=new Date(s);if(Number.isNaN(date.getTime()))return '时间未明确';return new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Shanghai'}).format(date);};
export const types={PUBLIC_INSTITUTION_JOB:'事业单位',STATE_OWNED_ENTERPRISE_JOB:'国央企',CIVIL_SERVICE:'考公',GRASSROOTS_PROGRAM:'基层项目',YOUTH_POLICY_BENEFIT:'人才政策',POSTGRAD_RECOMMENDATION:'升学',ADMISSION_CHANGE:'招生信息',COMPETITION:'竞赛',RESEARCH_PROGRAM:'科研',SCHOLARSHIP:'奖学金',YOUTH_DEVELOPMENT_PROGRAM:'成长与实践'};
export const statusText={PENDING:'待审核',APPROVED:'已收录',REJECTED:'不通过',CURRENT:'已收录',UPDATE_PENDING:'更新待收录',WITHDRAWN:'已撤回',QUEUED:'等待调查',RUNNING:'处理中',RECOVERY_QUEUED:'等待恢复',NEEDS_RECOVERY:'待恢复',FAILED:'处理失败',READY:'结果已接收',CANCELLED:'已停止后续处理',SAVED:'已收藏',PREPARING:'准备中',APPLIED:'已申请',WAITING:'等待结果',COMPLETED:'已完成',DISMISSED:'暂不考虑'};
export const tag=(text,color='')=>`<span class="pill ${color}">${e(text)}</span>`;
export const outside=(url,label='官方原文')=>url&&/^https?:\/\//.test(url)?`<a class="text-btn" href="${e(url)}" target="_blank" rel="noopener noreferrer">${e(label)} ${icon('external','sm')}</a>`:'';
export function go(url,replace=false){if(!url.startsWith('/')||url.startsWith('//'))url='/';history[replace?'replaceState':'pushState']({},'',url);window.dispatchEvent(new Event('routechange'));}
export async function api(path,{method='GET',data,raw}={}){
 const headers={};if(method!=='GET')headers['X-CSRF-Token']=state.csrf;
 let body;if(raw){body=raw;headers['Content-Type']='application/zip';}else if(data!==undefined){body=JSON.stringify(data);headers['Content-Type']='application/json';}
 let res;try{res=await fetch(path,{method,headers,body,credentials:'same-origin',cache:'no-store'});}catch(cause){const err=new Error('网络连接中断，请检查连接后重试');err.network=true;throw err;}
 const ct=res.headers.get('content-type')||'';let val=ct.includes('json')?await res.json():await res.text();
 if(!res.ok){let msg=val.message||(Array.isArray(val.detail)?'填写内容不符合要求，请检查各项输入':val.detail)||'操作未完成，请稍后重试';const err=new Error(msg);err.status=res.status;err.code=val.error;throw err;}return val;
}
let timer;
export function toast(message,kind='info'){const node=$('#toast');node.textContent=message;node.dataset.kind=kind;node.classList.add('visible');clearTimeout(timer);timer=setTimeout(()=>node.classList.remove('visible'),5000);}
export function bind(selector,event,handler,scope=document){$$(selector,scope).forEach(el=>el.addEventListener(event,async ev=>{
 ev.preventDefault();const button=el instanceof HTMLButtonElement?el:(event==='submit'?$('button[type=submit]',el):null);
 if(button?.disabled)return;if(button){button.disabled=true;button.classList.add('is-loading');button.setAttribute('aria-busy','true');}
 try{await handler(ev,el);}catch(err){toast(err.message,'error');}finally{if(button?.isConnected){button.disabled=false;button.classList.remove('is-loading');button.removeAttribute('aria-busy');}}
}));}
export function modal(title,body,handler,submit='确定',danger=false){
 const d=$('#dialog');if(d.open)d.close();const heading='dialog-title-'+Date.now();d.setAttribute('aria-labelledby',heading);d.innerHTML=`<form class="dialog-form"><div class="between"><h2 id="${heading}">${e(title)}</h2><button type="button" class="icon-btn close-dialog" aria-label="关闭">${icon('x')}</button></div><div class="dialog-body">${body}</div><div class="dialog-footer"><button type="button" class="btn close-dialog">取消</button>${handler?`<button type="submit" class="btn ${danger?'danger':'primary'}">${e(submit)}</button>`:''}</div></form>`;
 $$('.close-dialog',d).forEach(b=>b.onclick=()=>d.close());
 if(handler)bind('form','submit',async(ev,form)=>{await handler(new FormData(form),form);d.close();},d);
 d.showModal();requestAnimationFrame(()=>{const focusable=d.querySelector('input:not([disabled]),select:not([disabled]),textarea:not([disabled]),button:not([disabled]),a[href]');focusable?.focus();});
}
export function empty(title,body='',link='',label='查看机会总览'){return `<div class="empty surface"><div class="empty-icon">${icon('spark')}</div><h3>${e(title)}</h3>${body?`<p>${e(body)}</p>`:''}${link?`<a class="btn primary" href="${e(link)}" data-nav>${e(label)}</a>`:''}</div>`;}
export function pagination(offset,total,limit,url){return total>limit?`<nav class="pagination" aria-label="分页"><span class="muted">${offset+1}–${Math.min(offset+limit,total)} / ${total}</span><div class="row gap8">${offset?`<a class="btn" data-nav href="${e(url(Math.max(0,offset-limit)))}">上一页</a>`:''}${offset+limit<total?`<a class="btn" data-nav href="${e(url(offset+limit))}">下一页</a>`:''}</div></nav>`:'';}
export const targetKinds={POSITION:'岗位',TRACK:'赛道',PROGRAM_TIER:'项目档次',REGION_VARIANT:'地区分项',DEFAULT_SINGLETON:'单项机会'};
export function contextualTargetLabel(type,kind,rawType=''){
 const maps={
  COMPETITION:{POSITION:'参赛分项',TRACK:'赛道',PROGRAM_TIER:'组别 / 级别',REGION_VARIANT:'赛区',DEFAULT_SINGLETON:'赛事'},
  RESEARCH_PROGRAM:{POSITION:'研究岗位',TRACK:'研究方向',PROGRAM_TIER:'项目分项',REGION_VARIANT:'地区项目',DEFAULT_SINGLETON:'科研项目'},
  SCHOLARSHIP:{POSITION:'资助分项',TRACK:'资助类别',PROGRAM_TIER:'资助档次',REGION_VARIANT:'地区资助',DEFAULT_SINGLETON:'奖学金'},
  YOUTH_POLICY_BENEFIT:{POSITION:'支持分项',TRACK:'政策类别',PROGRAM_TIER:'支持档次',REGION_VARIANT:'地区政策',DEFAULT_SINGLETON:'政策 / 补贴'},
  POSTGRAD_RECOMMENDATION:{POSITION:'招生分项',TRACK:'项目方向',PROGRAM_TIER:'项目类别',REGION_VARIANT:'地区 / 校区',DEFAULT_SINGLETON:'升学项目'},
  ADMISSION_CHANGE:{POSITION:'招生分项',TRACK:'项目方向',PROGRAM_TIER:'项目类别',REGION_VARIANT:'地区 / 校区',DEFAULT_SINGLETON:'招生项目'},
 };
 if(type==='YOUTH_DEVELOPMENT_PROGRAM'&&kind==='POSITION')return String(rawType).includes('实习')?'实习岗位':'实践岗位';
 return maps[type]?.[kind]||targetKinds[kind]||'具体分项';
}
export function actionTime(c,fallback='时间见详情'){
 const readiness=c?.time_readiness||{},m=c?.primary_milestone||{};
 if(readiness.state==='ROLLING')return {text:'滚动受理',state:'ROLLING',safe:false};
 if(readiness.state==='PENDING_UPDATE')return {text:'时间更新待收录',state:'PENDING_UPDATE',safe:false};
 if(readiness.state==='CONFLICT')return {text:'时间存在冲突',state:'CONFLICT',safe:false};
 if(readiness.state==='PARTIAL')return {text:'关键截止待确认',state:'PARTIAL',safe:false};
 if(m.date){const suffix=m.time?` ${m.time}`:'';return {text:`${m.date}${suffix}`,state:'READY',safe:true};}
 if(c?.deadline)return {text:String(c.deadline),state:'READY',safe:true};
 return {text:fallback,state:readiness.state||'UNKNOWN',safe:false};
}
export function card(c){const parent=c.parent_announcement?.title,p=c.presentation||{};const typeLabel=c.presentation?.type_label||types[c.type]||'机会',targetLabel=c.presentation?.target_label||targetKinds[c.target_kind]||'行动机会',timeLabel=c.presentation?.time_label||'报名时间',unknownTime=c.presentation?.unknown_time_label||'时间见详情',action=actionTime(c,unknownTime);return `<article class="op-card"><div class="between"><div class="row gap6 wrap">${tag(typeLabel,'blue')}${c.target_kind?tag(targetLabel,''):''}${c.code?tag('编号 '+c.code,''):''}</div>${c.status==='UPDATE_PENDING'?tag('更新待收录','amber'):''}</div><h3><a href="/app/opportunity/${e(c.id)}" data-nav>${e(c.title)}</a></h3><div class="row gap6 muted small">${icon('globe','sm')}<span>${e(c.issuer)}</span></div>${c.region?`<div class="card-region">${icon('pin','sm')}${e(c.region)}</div>`:''}${parent?`<div class="muted tiny mt8 text-flow">来自 ${e(parent)}</div>`:''}${c.reasons?`<div class="relevance">${icon('spark','sm')}<span>${e(c.reasons[0])}</span></div>`:''}${c.notes?.length?`<div class="card-note">${icon('info','sm')}${e(c.notes.find(x=>x.includes('报名')||x.includes('申请')||x.includes('受理'))||c.notes[0])}</div>`:''}<div class="op-foot"><span>${icon('calendar','sm')}${action.safe?`${e(timeLabel)} ${e(action.text)}`:e(action.text)}</span><a href="/app/opportunity/${e(c.id)}" data-nav aria-label="查看${e(c.title)}">${icon('arrow','sm')}</a></div></article>`;}
export function field(f,compact=false){return `<div class="fact" id="field-${e(f.id)}"><div class="fact-label">${e(f.label)} ${f.excluded?tag('不采用','red'):''}</div><div class="fact-value text-flow ${f.excluded?'excluded-value':''}">${e(f.value||'当前材料尚未提取此项')}</div>${f.value_total>f.value.length?`<button class="text-btn field-text-more" data-field="${e(f.id)}" data-offset="${f.value.length}">继续阅读</button>`:''}${compact?'':(f.notes||[]).map(n=>`<div class="fact-note">${icon('info','sm')}<span>${e(n)}</span></div>`).join('')}${f.evidence?.length||(compact&&f.notes?.length)?`<details class="evidence"><summary>${compact?'说明与来源':'查看依据'} ${!compact&&f.quote_located?tag('引用已定位','green'):''}</summary>${compact&&f.notes?.length?`<ul class="field-notes">${[...new Set(f.notes)].map(n=>`<li>${e(n)}</li>`).join('')}</ul>`:''}${(f.evidence||[]).map(ref=>`<div class="quote"><p class="text-flow">${e(ref.quote||'未提供引用片段')}</p><div class="between"><span class="muted small">${e(Object.entries(ref.locator||{}).map(([k,v])=>`${k} ${v}`).join(' · '))}</span>${outside(ref.url,'来源')}</div></div>`).join('')}</details>`:''}</div>`;}
export function fields(items,compact=false){const sections=[...new Set(items.map(f=>f.section||'其他说明'))];return sections.map(s=>`<section class="field-section"><h3>${e(s)}</h3>${items.filter(f=>(f.section||'其他说明')===s).map(f=>field(f,compact)).join('')}</section>`).join('');}
export function child(c,type='',rawType=''){const label=c.kind==='GROUP'?'分组 / 共同内容':contextualTargetLabel(type,c.kind,rawType);return `<details class="unit-detail" data-unit="${e(c.id)}"><summary><span>${tag(label,'blue')} <strong>${e(c.name)}</strong></span>${icon('down','sm')}</summary><div class="unit-fields">${c.code?`<p class="muted small">编号 ${e(c.code)}</p>`:''}${fields(c.fields||[])}</div>${c.field_total>c.fields.length?`<button class="btn unit-more" data-unit="${e(c.id)}" data-offset="${c.fields.length}">更多内容</button>`:''}</details>`;}

// A single delegated listener covers newly loaded rows and preserves textual data.
export function prepareTextPaging(base,version,item=0){
 const main=$('#main-content');main.dataset.contentBase=base;main.dataset.contentVersion=version;main.dataset.contentItem=item;
}
document.addEventListener('click',async ev=>{
 const b=ev.target.closest('.field-text-more');if(!b)return;ev.preventDefault();if(b.disabled)return;
 const main=b.closest('#main-content');if(!main?.dataset.contentBase)return;b.disabled=true;
 try{const off=Number(b.dataset.offset),q=new URLSearchParams({field:b.dataset.field,offset:off,version:main.dataset.contentVersion,item:main.dataset.contentItem});const r=await api(main.dataset.contentBase+'/text?'+q);b.previousElementSibling.textContent+=r.text;b.dataset.offset=off+r.text.length;if(Number(b.dataset.offset)>=r.total)b.remove();}
 catch(err){toast(err.message);}finally{if(b.isConnected)b.disabled=false;}
});
export function prepareReviewPaging(base,version,item){
 prepareTextPaging(base,version,item);
 const query=(offset,unit='')=>new URLSearchParams({offset,unit,version,item});
 bind('#review-fields-more','click',async(_,b)=>{const off=Number(b.dataset.offset),r=await api(base+'/content?'+query(off));$('#review-fields').insertAdjacentHTML('beforeend',fields(r.items));b.dataset.offset=off+r.items.length;if(Number(b.dataset.offset)>=r.total)b.remove();});
 const units=()=>$$('.unit-more:not([data-bound])').forEach(b=>{b.dataset.bound='1';b.addEventListener('click',async()=>{b.disabled=true;try{const off=Number(b.dataset.offset),r=await api(base+'/content?'+query(off,b.dataset.unit));$('.unit-fields',b.parentElement).insertAdjacentHTML('beforeend',fields(r.items));b.dataset.offset=off+r.items.length;if(Number(b.dataset.offset)>=r.total)b.remove();}catch(err){toast(err.message);}finally{if(b.isConnected)b.disabled=false;}});});
 units();bind('#review-units-more','click',async(_,b)=>{const off=Number(b.dataset.offset),r=await api(base+'/units?'+query(off));$('#review-units').insertAdjacentHTML('beforeend',r.items.map(child).join(''));b.dataset.offset=off+r.items.length;if(Number(b.dataset.offset)>=r.total)b.remove();units();});
}
