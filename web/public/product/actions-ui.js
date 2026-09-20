import {$,e,icon,api,bind,modal,toast,go,tag,time,statusText,pagination,empty,actionTime} from './core.js';
import {detailURL} from './experience-core.js';
const statuses=['SAVED','PREPARING','APPLIED','WAITING','COMPLETED','DISMISSED'];
const labels={SAVED:'已收藏',PREPARING:'准备中',APPLIED:'已申请',WAITING:'等待结果',COMPLETED:'已完成',DISMISSED:'暂不考虑'};
const pageURL=(params,changes={})=>{const q=new URLSearchParams(params);for(const [k,v] of Object.entries(changes))v?q.set(k,String(v)):q.delete(k);return '/app/actions'+(q.size?'?'+q:'');};

export async function showPreparation(id){
 const result=await api('/api/me/actions/'+encodeURIComponent(id)+'/items');
 const itemRows=items=>items.length?items.map(x=>`<div class="preparation-item"><button type="button" class="item-toggle icon-btn" data-id="${e(x.id)}" aria-label="${x.done?'取消完成':'标记完成'} ${e(x.text)}" aria-pressed="${x.done}">${icon(x.done?'checkcircle':'circle')}</button><div class="grow"><strong class="${x.done?'item-done':''}">${e(x.text)}</strong><p class="muted tiny">${x.origin==='USER'?'我添加的事项':'来自已保存材料'}${x.material_changed?' · 材料已变化，请重新核对':''}</p></div><button type="button" class="text-btn item-edit" data-id="${e(x.id)}">编辑</button><button type="button" class="text-btn item-delete" data-id="${e(x.id)}">删除</button></div>`).join(''):'<p class="muted">还没有准备事项。</p>';
 let rows=result.items,key=crypto.randomUUID();
 modal('个人准备清单',`<p class="muted small">记录自己的下一步，不改变公告内容或资格判断。</p><div id="preparation-items" class="mt16">${itemRows(rows)}</div>${result.target_available?'<div class="form-field mt20"><label for="item-text">新增事项</label><input id="item-text" name="text" required maxlength="500" placeholder="例如：核对报名材料，整理作品集"></div>':'<p class="note warning mt20">机会已撤回，仅保留已有清单。</p>'}`,result.target_available?async f=>{await api('/api/me/actions/'+id+'/items',{method:'POST',data:{text:f.get('text'),request_key:key}});toast('准备事项已保存');}:null,'添加事项');
 const draw=()=>{
  $('#preparation-items').innerHTML=itemRows(rows);
  bind('.item-toggle','click',async(_,b)=>{const x=rows.find(x=>x.id===b.dataset.id),updated=await api(`/api/me/actions/${id}/items/${x.id}`,{method:'PATCH',data:{expected_version:x.version,done:!x.done}});rows=rows.map(y=>y.id===x.id?updated:y);draw();});
  bind('.item-delete','click',async(_,b)=>{
   const x=rows.find(x=>x.id===b.dataset.id);
   // Second click confirms in place; no native confirm or nested dialog.
   if(b.dataset.confirm!=='yes'){b.dataset.confirm='yes';b.textContent='确认删除';return;}
   await api(`/api/me/actions/${id}/items/${x.id}?expected_version=${x.version}`,{method:'DELETE'});rows=rows.filter(y=>y.id!==x.id);draw();
  });
  bind('.item-edit','click',(_,b)=>{
   const x=rows.find(x=>x.id===b.dataset.id);
   modal('编辑准备事项',`<div class="form-field"><label for="edit-preparation">事项</label><textarea id="edit-preparation" name="text" required maxlength="500">${e(x.text)}</textarea></div>`,async f=>{await api(`/api/me/actions/${id}/items/${x.id}`,{method:'PATCH',data:{expected_version:x.version,text:f.get('text')}});toast('事项已更新');},'保存事项');
  });
 };draw();
}
export async function renderActions(params){
 const view=params.get('view')==='list'?'list':'board',status=statuses.includes(params.get('status'))?params.get('status'):'',offset=Math.max(0,Number(params.get('offset'))||0);
 const query=new URLSearchParams({status,offset,limit:30}),[r,digest]=await Promise.all([api('/api/me/action-board?'+query),api('/api/me/weekly-digest')]),back=pageURL(params);
 const row=x=>{const c=x.opportunity,a=actionTime(c),readonly=x.legacy_scope||c.status==='WITHDRAWN';return `<article class="action-card"><div class="between">${tag(labels[x.status],x.status==='COMPLETED'?'green':'blue')}${c.status==='UPDATE_PENDING'?tag('更新待收录','amber'):''}</div><h3><a href="${e(x.legacy_scope?'/app/announcement/'+c.id:detailURL(c.id,back))}" data-nav>${e(c.title)}</a></h3><p class="muted small">${c.status==='WITHDRAWN'?'该机会已撤回':e(a.text)}</p>${x.legacy_scope?'<p class="note info">旧版公告级记录，未自动分配到具体岗位。</p>':''}${x.note?`<p class="action-note-copy">${e(x.note)}</p>`:''}<label class="action-select-label">行动状态<select class="action-status" data-id="${e(c.id)}" ${readonly?'disabled':''}>${statuses.map(s=>`<option value="${s}" ${s===x.status?'selected':''}>${labels[s]}</option>`).join('')}</select></label><div class="action-card-buttons">${!x.legacy_scope?`<button class="btn sm preparation-open" data-id="${e(c.id)}">准备清单</button><button class="text-btn action-history" data-id="${e(c.id)}">时间线</button>`:''}${!readonly?`<button class="text-btn action-note" data-id="${e(c.id)}">进展与结果</button><button class="text-btn action-remove" data-id="${e(c.id)}">移出</button>`:''}</div></article>`;};
 let body=`<div class="between wrap gap12"><h1>收藏与行动</h1><nav class="row gap8" aria-label="行动视图"><a class="btn ${view==='board'?'primary':''}" data-nav href="${e(pageURL(params,{view:'board'}))}">看板</a><a class="btn ${view==='list'?'primary':''}" data-nav href="${e(pageURL(params,{view:'list'}))}">列表</a></nav></div><nav class="action-filters" aria-label="行动状态"><a class="chip ${!status?'active':''}" href="${e(pageURL(params,{status:'',offset:0}))}" data-nav>全部 ${Object.values(r.counts).reduce((a,b)=>a+b,0)}</a>${statuses.map(s=>`<a class="chip ${status===s?'active':''}" href="${e(pageURL(params,{status:s,offset:0}))}" data-nav>${labels[s]} ${r.counts[s]||0}</a>`).join('')}</nav>`;
 body+=digestCard(digest);
 if(view==='board')body+=`<div class="action-board">${(status?[status]:statuses).map(s=>`<section class="action-column"><div class="between"><h2>${labels[s]}</h2><span class="muted small">${r.counts[s]||0}</span></div>${r.items.filter(x=>x.status===s).map(row).join('')||'<p class="muted small">本页没有此状态的记录</p>'}</section>`).join('')}</div>`;
 else body+=`<div class="action-list-view">${r.items.map(row).join('')||empty('还没有行动记录','去机会总览收藏一项感兴趣的机会。','/app/overview')}</div>`;
 body+=pagination(offset,r.total,30,n=>pageURL(params,{offset:n}));
 const after=()=>{
  bind('.preparation-open','click',(_,b)=>showPreparation(b.dataset.id));
  bind('.action-status','change',async(_,b)=>{const x=r.items.find(x=>x.opportunity.id===b.dataset.id);try{await api('/api/me/actions/'+b.dataset.id,{method:'PUT',data:{status:b.value,note:x.note}});go(back);}catch(err){b.value=x.status;throw err;}});
  bind('.action-history','click',async(_,b)=>{const h=await api('/api/me/actions/'+b.dataset.id+'/history');modal('行动时间线',`<div class="action-timeline">${(h.events||[]).map(x=>`<article><strong>${e(statusText[x.to_status]||x.to_status)}</strong><span class="muted small"> · ${e(time(x.created_at))}</span><p>${e(x.note||'')}</p></article>`).join('')||'<p>还没有历史记录。</p>'}</div>`,null);});
  bind('.action-remove','click',(_,b)=>modal('移出我的行动','<p>移出后停止相关截止提醒，已有行动历史和准备事项保留。</p>',async()=>{await api('/api/me/actions/'+b.dataset.id,{method:'DELETE'});go(back);},'确认移出',true));
  bind('.action-note','click',(_,b)=>{const x=r.items.find(x=>x.opportunity.id===b.dataset.id);modal('进展与结果',`<div class="form-field"><label>准备事项或申请进展</label><textarea name="note" maxlength="2000">${e(x.note)}</textarea></div><div class="form-field"><label>以前知道这个机会吗</label><select name="previously_known"><option value="">暂不填写</option><option value="false">以前不知道</option><option value="true">以前知道</option></select></div><div class="form-field"><label>这项机会对你有用吗</label><select name="useful"><option value="">暂不填写</option><option value="true">有用</option><option value="false">暂时没用</option></select></div><div class="form-field"><label>暂不行动的原因</label><select name="action_reason"><option value="">暂不填写</option>${Object.entries({NOT_INTERESTED:'方向不感兴趣',NOT_ELIGIBLE:'条件不符合',TOO_FAR:'地点不合适',TOO_HARD:'准备难度太高',INFO_INSUFFICIENT:'信息不足',TIME_CONFLICT:'时间冲突',OTHER:'其他'}).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></div><div class="form-field"><label>最终结果</label><select name="outcome"><option value="">暂不填写</option>${Object.entries({APPLIED:'已申请',INTERVIEW:'获得面试 / 进入下一轮',ACCEPTED:'已录取 / 入选',REJECTED:'未通过',NO_RESULT:'等待结果',ABANDONED:'决定放弃'}).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></div><div class="form-field"><label>补充反馈</label><textarea name="comment" maxlength="2000"></textarea></div>`,async f=>{
   await api('/api/me/actions/'+b.dataset.id,{method:'PUT',data:{status:x.status,note:f.get('note')}});
   const feedback={};for(const k of ['previously_known','useful'])if(f.get(k)!=='')feedback[k]=f.get(k)==='true';for(const k of ['action_reason','outcome','comment'])if(f.get(k))feedback[k]=f.get(k);
   if(Object.keys(feedback).length)try{await api('/api/me/feedback/'+b.dataset.id,{method:'POST',data:feedback});}catch(err){throw new Error('进展已保存，但反馈尚未保存：'+err.message);}
   go(back);toast('进展与反馈已保存');
  },'保存进展');});
 };
 return {body,after};
}
export async function renderNotifications(params){
 const unread=params.get('unread')==='true',offset=Math.max(0,Number(params.get('offset'))||0),r=await api('/api/me/notification-list?'+new URLSearchParams({unread,offset,limit:30}));
 const url=n=>'/app/notifications?'+new URLSearchParams({unread,offset:n});
 const body=`<div class="between wrap gap12"><div><h1>消息与提醒</h1><p class="muted small mt8">${r.unread_count} 条未读</p></div><div class="row wrap gap8"><button class="btn" id="show-weekly-digest">本周机会摘要</button><button class="btn" id="batch-read" ${r.items.some(x=>x.state!=='READ')?'':'disabled'}>本页全部标为已读</button></div></div><nav class="row gap12 mt20 mb16" aria-label="消息筛选"><a class="chip ${!unread?'active':''}" href="/app/notifications" data-nav>全部</a><a class="chip ${unread?'active':''}" href="/app/notifications?unread=true" data-nav>只看未读</a></nav>${r.items.map(x=>`<article class="notice-row ${x.state==='READ'?'read':''}"><div class="between"><div>${tag({DEADLINE:'截止提醒',CHANGE:'机会变化',WEEKLY:'每周摘要'}[x.kind]||'消息','blue')}<h2>${e(x.title)}</h2></div><span class="muted tiny">${e(time(x.created_at))}</span></div><p>${e(x.body)}</p><div class="between">${x.opportunity_id?`<a href="${e(detailURL(x.opportunity_id))}" data-nav>查看机会</a>`:''}${x.state!=='READ'?`<button class="text-btn mark-read" data-id="${e(x.id)}">标为已读</button>`:''}</div></article>`).join('')||empty('暂时没有新消息','重要变化与截止提醒会在这里出现。')}${pagination(offset,r.total,30,url)}`;
 return {body,after:()=>{
  bind('#show-weekly-digest','click',async()=>{const d=await api('/api/me/weekly-digest');modal('本周机会摘要',digestCard(d),null);});
  bind('#batch-read','click',async()=>{await api('/api/me/notifications/read',{method:'POST',data:{ids:r.items.filter(x=>x.state!=='READ').map(x=>x.id)}});go(url(offset));});
  bind('.mark-read','click',async(_,b)=>{await api('/api/me/notifications/'+b.dataset.id+'/read',{method:'POST'});go(url(offset));});
 }};
}

function digestCard(d){
 const a=d.action_summary||{};
 return `<section class="weekly-digest-card"><div class="between"><h2>本周机会摘要</h2>${tag(d.period_key||'本周','blue')}</div><div class="weekly-digest-grid"><div><strong>${(a.SAVED||0)+(a.PREPARING||0)+(a.APPLIED||0)+(a.WAITING||0)}</strong><span>进行中的行动</span></div><div><strong>${(d.due_soon||[]).length}</strong><span>7天内截止</span></div><div><strong>${(d.changes||[]).length}</strong><span>机会变化</span></div><div><strong>${(d.new_opportunities||[]).length}</strong><span>值得继续了解</span></div></div></section>`;
}
