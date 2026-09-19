import {$,$$,e,icon,time,tag,outside,go,api,bind,toast,modal,empty,pagination} from './core.js';

const base='/api/manage/scout';
const drafts=new Map();
const stateLabel={PREPARING:'正在读取',PREPARED:'待接收',COMMITTED:'已接收',INVALID:'文件有误',RECEIVED:'已接收为候选',CONFLICT:'批次内容冲突',NOT_SELECTED:'未接收',PENDING:'待接收'};
const opinion={PROPOSE_STAGING:'建议接收',DEFER:'暂缓',REJECT:'不采用'};
const issueLabel={INVALID_CANDIDATE_ID:'研究编号格式不正确',FIRST_SEEN_CHANGED:'研究记录中的首次发现时间发生变化',INVALID_EVIDENCE_REFERENCE:'研究依据引用格式不完整',MISSING_BRIEF_EVIDENCE_REFERENCE:'采集建议的部分研究依据未提供',REFERENCE_TEXT_NORMALIZATION_PROPOSAL:'已保留原句，引用编号按明确文字关联',SEED_NORMALIZATION_PROPOSAL:'已从原记录识别入口，原文仍保留',SYSTEM_MAPPING_UNVERIFIED:'原文件中的系统映射尚未认证',BRIEF_SOURCE_OUTSIDE_SELECTION:'采集建议关联本次范围外的来源',ATTACHMENT_MISSING:'部分关联附件未在包内找到',ATTACHMENT_UNREAD:'部分附件未读取',INVALID_SEED:'入口尚不能确定',RUN_CONTENT_CONFLICT:'同批次内容冲突',MISSING_CANDIDATE_KEY:'缺少候选标识',MULTIPLE_SEEDS:'有多个入口',BRIEF_NOT_IN_SELECTED_HANDOFFS:'未提供采集建议',MISSING_EVIDENCE_REFERENCE:'部分研究依据未提供',SEED_CHANGED_ACROSS_VERSIONS:'入口发生变化',SCORE_ARITHMETIC_MISMATCH:'评分计算不一致',UNVERIFIED_SYSTEM_ID_CLAIM:'外部系统编号未认证'};
const fieldLabel={source_ref:'关联来源',brief_key:'建议编号',revision:'版本',base_revision:'前一版本',recommended_seed:'推荐入口',navigation_advice:'导航建议',source_topology:'页面结构',opportunity_pattern:'机会组织方式',discovery_strategy:'发现新公告',source_network:'关联来源',evidence_hotspots:'重点依据位置',attachment_pattern:'附件特点',change_pattern:'更正与更新',observed_access_shape:'访问方式',known_obstacles:'已知障碍',stop_escalation_rule:'停止与交接条件',agent_capability_needs:'所需能力',expected_candidate_evidence_package:'预期材料',suggested_revisit_pattern:'复查建议',recon_evidence:'研究依据',last_checked_at:'上次研究时间',scout_confidence:'研究者把握程度',source_role:'来源角色',authority_assessment:'来源身份线索',demand_themes:'需求方向',opportunity_types:'机会类型',target_youth:'适用人群',uncertainties:'未确定事项',source_name:'来源名称',institution:'机构',evidence_refs:'研究依据',candidate_key:'研究编号',recommendation:'研究建议'};
function heading(t,sub='',action=''){return `<div class="work-title"><div><h1>${e(t)}</h1>${sub?`<p>${e(sub)}</p>`:''}</div><div class="row gap8 wrap">${action}</div></div>`;}
const knownValues={OFFICIAL_PRIMARY:'官方一手来源',OFFICIAL_AGGREGATOR:'官方汇总来源',TRUSTED_SECONDARY:'可信线索源',COMMUNITY_SIGNAL:'社区线索',PRIORITY_ADD:'优先关注',EXPLORE:'继续探索',DEFER:'暂缓',REJECT:'不采用'};
function value(v){if(v===null||v===undefined)return '—';if(Array.isArray(v)&&v.every(x=>typeof x!=='object'))return v.join('、');if(typeof v==='object')return JSON.stringify(v,null,2);return knownValues[v]||String(v);}
function record(obj){return `<dl class="scout-record">${Object.entries(obj||{}).map(([k,v])=>`<div><dt>${e(fieldLabel[k]||k)}</dt><dd class="text-flow">${e(value(v))}</dd></div>`).join('')}</dl>`;}
function stats(b){const s=b.summary||{};return `<div class="scout-stats">${[['候选来源',s.candidate_groups||0],['历史观察',s.source_versions||0],['采集建议',s.brief_versions||0],['研究依据',s.evidence_records||0]].map(([l,n])=>`<div><strong>${n}</strong><span>${l}</span></div>`).join('')}</div>`;}
function fileLink(id,name,label){return `<a class="text-btn" href="${base}/batches/${e(id)}/file?name=${encodeURIComponent(name)}">${icon('download','sm')}${e(label||name.split('/').pop())}</a>`;}
function feedbackLink(id){return `<a class="btn" href="${base}/batches/${e(id)}/feedback">${icon('download','sm')}下载系统反馈</a>`;}

export async function uploadResearch(file){
 if(!file?.size)throw new Error('请选择研究交接 ZIP 或 Handoff.json');
 if(!/\.(zip|json)$/i.test(file.name))throw new Error('请选择 ZIP 或 JSON 文件');
 if(file.size>100*1024*1024)throw new Error('文件超过100MiB，请分批提交');
 const r=await api(base+'/previews?filename='+encodeURIComponent(file.name),{method:'POST',raw:file});
 go('/manage/source-imports/'+r.id);
 toast(r.status==='INVALID'?'原件已保留，请查看文件问题':'研究文件已读取');
}
function uploadDialog(){modal('导入研究包',`<div class="form-field"><label for="scout-file">研究交接 ZIP / Handoff.json</label><input id="scout-file" name="file" type="file" accept=".zip,.json" required></div><p class="small muted">100MiB 以内。上传不会启用来源或开始调查。</p>`,async f=>uploadResearch(f.get('file')),'上传并检查');}

export async function renderScout(path,params){
 let body='',after=()=>{};
 const parts=path.split('/').filter(Boolean),id=parts[2],gid=parts[4];
 if(!id){
  const offset=Math.max(0,Number(params.get('offset')||0)),r=await api(base+'/batches?offset='+offset);
  body=heading('来源资产','外部研究 · 候选接收 · 采集来源',`<a class="btn" href="/manage/sources" data-nav>来源管理</a><button id="scout-upload" class="btn primary">${icon('upload','sm')}导入研究包</button>`)+
   `<section id="scout-drop" class="scout-drop"><div class="scout-upload-icon">${icon('upload')}</div><div><h2>将研究包交给机会星图</h2><p>拖入工具导出的 ZIP，或选择 Handoff.json、WB 研究包</p></div><button id="scout-choose" class="btn">选择文件</button><input id="scout-inline-file" type="file" accept=".zip,.json" hidden></section>`+
   `<div class="scout-section-title"><h2>提交记录</h2><span class="muted small">${r.total} 个批次</span></div>`+
   (r.items.length?`<div class="work-table-wrap"><table class="work-table"><thead><tr><th>研究批次</th><th>候选来源</th><th>接收结果</th><th>提交时间</th><th></th></tr></thead><tbody>${r.items.map(b=>`<tr><td><a class="record-title" data-nav href="/manage/source-imports/${e(b.id)}">${e(b.filename)}</a><span class="meta">${b.summary?.source_versions||0} 条历史观察 · ${b.summary?.brief_versions||0} 份采集建议</span></td><td><strong>${b.summary?.candidate_groups||0}</strong></td><td>${tag(stateLabel[b.status]||b.status,b.status==='COMMITTED'?'green':b.status==='INVALID'?'red':'blue')}${b.receipt?`<span class="meta">${b.receipt.received} 个接收 · ${b.receipt.conflicts} 个冲突</span>`:''}</td><td class="muted small">${e(time(b.created_at))}</td><td><a class="text-btn" data-nav href="/manage/source-imports/${e(b.id)}">查看 ${icon('chevron','sm')}</a></td></tr>`).join('')}</tbody></table></div>`:empty('还没有提交记录','导入外部研究文件后，在这里查看候选和系统反馈。'))+
    pagination(offset,r.total,20,x=>'/manage/source-imports?offset='+x);
  after=()=>{
   bind('#scout-upload','click',uploadDialog);bind('#scout-choose','click',()=>$('#scout-inline-file').click());
   $('#scout-inline-file').addEventListener('change',async ev=>{try{await uploadResearch(ev.target.files[0]);}catch(err){toast(err.message);}});
   const drop=$('#scout-drop');drop.addEventListener('dragover',ev=>{ev.preventDefault();drop.classList.add('dragging');});drop.addEventListener('dragleave',()=>drop.classList.remove('dragging'));
   drop.addEventListener('drop',async ev=>{ev.preventDefault();drop.classList.remove('dragging');if(ev.dataTransfer.files.length!==1)return toast('每次选择一个交接包；多份原件请先打包');try{await uploadResearch(ev.dataTransfer.files[0]);}catch(err){toast(err.message);}});
  };
 }else if(gid){
  const g=await api(`${base}/batches/${id}/candidates/${gid}`),b=await api(`${base}/batches/${id}`),v=g.projection;
  const names=[...new Map([...(g.existing_sources||[]),...(g.bound_source?[g.bound_source]:[])].map(x=>[x.id,x])).values()];
  const usable=g.state==='RECEIVED'&&!g.blocking;
  const chosenBrief=g.briefs.find(x=>x.run_key===v.current.run_key)?.id||'';
  body=`<a class="back-link" data-nav href="/manage/source-imports/${e(id)}">${icon('back','sm')}返回研究批次</a>`+
    heading(String(g.name),g.namespace+' / '+g.candidate_key)+
    `<div class="scout-detail-grid"><div><section class="manage-panel"><div class="between"><h2>来源档案</h2>${tag(g.binding_current?'已关联来源':stateLabel[g.state]||g.state,g.binding_current?'green':'blue')}</div><div class="scout-seeds">${g.seed_urls.map(u=>outside(u,u)).join('')}</div>${record(Object.fromEntries(Object.entries(v.current.payload).filter(([k])=>!['score_breakdown','score_total','recommended_seed','system_source_id'].includes(k))))}</section>`+
    `<section class="manage-panel"><div class="between"><h2>采集建议</h2><span class="small muted">${g.briefs.length} 个版本</span></div>${g.briefs.length?g.briefs.map((br,i)=>`<details class="scout-brief" ${br.id===chosenBrief?'open':''}><summary><strong>${e(br.key)}</strong><span>${e(br.run_key)}</span></summary>${record(br.payload)}</details>`).join(''):'<p class="muted">本批研究未提供采集建议。</p>'}</section>`+
    `<section class="manage-panel"><h2>研究依据</h2>${v.evidence_versions.map(ev=>`<details class="scout-brief"><summary>${e(ev.key)}<span>${e(ev.run_key)}</span></summary>${record(ev.payload)}</details>`).join('')||'<p class="muted">当前包没有可关联的研究依据。</p>'}</section>`+
    `<section class="manage-panel"><h2>历史观察</h2>${v.versions.map((x,i)=>`<details class="scout-brief"><summary>${e(x.run_key)}<span>${e(time(x.generated_at))}</span></summary>${record(x.payload)}</details>`).join('')}</section></div><aside class="scout-side">`+
    `<section class="manage-panel"><h2>处理情况</h2><div class="kv"><span>系统记录</span>${tag(stateLabel[g.state]||g.state,g.state==='RECEIVED'?'green':'amber')}</div><div class="kv"><span>外部意见</span><strong>${e(opinion[g.external_decision?.decision]||'未填写')}</strong></div>${g.external_decision?.reason?`<p class="small text-flow">${e(g.external_decision.reason)}</p>`:''}${g.issue_codes.length||g.conflict?`<div class="scout-issues">${[...(g.conflict?['同一研究批次已有不同内容，未覆盖历史记录']:[]),...g.issue_codes.map(x=>issueLabel[x]||'研究资料存在待核对项')].filter((v,i,a)=>a.indexOf(v)===i).map(x=>`<p>${icon('info','sm')}${e(x)}</p>`).join('')}</div>`:''}</section>`+
    `<section class="manage-panel"><h2>${g.bound_source?'来源配置':'批准采集来源'}</h2>${usable?`<form id="scout-approve"><div class="form-field"><label for="source-link">来源关联</label><select id="source-link" name="existing"><option value="">新建来源</option>${names.map(s=>`<option value="${e(s.id)}" ${g.bound_source?.id===s.id?'selected':''}>${e(s.name)} · 已有来源</option>`).join('')}</select></div><div class="form-field"><label for="scout-name">来源名称</label><input id="scout-name" name="name" maxlength="300" required value="${e(g.bound_source?.name||g.name)}"></div><div class="form-field"><label for="scout-url">主入口</label><select id="scout-url" name="url">${g.seed_urls.map(u=>`<option value="${e(u)}" ${g.external_decision?.primary_seed===u?'selected':''}>${e(u)}</option>`).join('')}</select></div><div class="form-field"><label for="scout-tier">来源角色</label><select id="scout-tier" name="tier">${[['TRUSTED_SECONDARY','可信线索源'],['OFFICIAL_PRIMARY','官方一手来源'],['OFFICIAL_AGGREGATOR','官方汇总来源'],['COMMUNITY_SIGNAL','社区线索']].map(([k,l])=>`<option value="${k}" ${g.bound_source?.tier===k?'selected':''}>${l}</option>`).join('')}</select></div><div class="form-field"><label for="scout-brief">选用采集建议</label><select id="scout-brief" name="brief"><option value="">暂不使用采集建议</option>${g.briefs.map(br=>`<option value="${e(br.id)}" ${chosenBrief===br.id?'selected':''}>${e(br.key)} · ${e(br.run_key)}</option>`).join('')}</select></div><div class="form-field"><label for="scout-hosts">允许访问的域名</label><textarea id="scout-hosts" name="hosts" rows="2" maxlength="5000">${e(g.bound_source?.allowed_hosts?.join('\n')||g.seed_urls.map(u=>new URL(u).hostname).filter((x,i,a)=>a.indexOf(x)===i).slice(0,1).join('\n'))}</textarea></div><div class="form-field"><label for="scout-reason">批准原因</label><textarea id="scout-reason" name="reason" required maxlength="1000" placeholder="记录本次采用依据"></textarea></div><label class="scout-check"><input name="enabled" type="checkbox">允许创建新的调查任务</label><p class="tiny muted">不自动开始调查，不设置定期采集。</p><button class="btn primary wide" type="submit">${g.bound_source?'确认更新来源配置':'批准为采集来源'}</button></form>`:`<p class="muted small">${g.state==='NOT_SELECTED'?'本次未接收此候选。':g.conflict?'该批次存在不同原件，暂不用于采集。':g.blocking?'来源身份或主入口尚不能确定。':'请先在批次页面接收此候选。'}</p>`}</section>`+
    `<section class="manage-panel"><h2>批次与原件</h2><p class="small text-flow">${e(b.filename)}</p>${fileLink(id,'upload/'+b.filename,'下载上传原包')}<details class="mt16"><summary class="small muted">查看包内材料</summary><div class="scout-materials">${g.materials.map(m=>`<div>${fileLink(id,m.name)}</div>`).join('')}</div></details>${b.status==='COMMITTED'?`<div class="mt16">${feedbackLink(id)}</div>`:''}</section></aside></div>`;
  after=()=>{
   bind('#source-link','change',async(_,select)=>{if(!select.value)return;const item=names.find(x=>x.id===select.value);const full=item;$('#scout-name').value=full.name;$('#scout-tier').value=full.tier||'OFFICIAL_PRIMARY';$('#scout-url').value=full.url;if(full.allowed_hosts)$('#scout-hosts').value=full.allowed_hosts.join('\n');});
   bind('#scout-approve','submit',async(_,form)=>{const f=new FormData(form),existing=names.find(x=>x.id===f.get('existing'));
    const payload={approval_version:g.approval_version,binding_version:g.binding_version,name:f.get('name'),url:f.get('url'),tier:f.get('tier'),brief_id:f.get('brief')||null,allowed_hosts:f.get('hosts').split(/[\s,，]+/).filter(Boolean),reason:f.get('reason'),enabled:f.has('enabled'),existing_source_id:existing?.id||null,expected_policy_version:existing?.policy_version??null,request_key:'approve-'+g.observation_id+'-'+crypto.randomUUID()};
    const r=await api(`${base}/observations/${g.observation_id}/approve`,{method:'POST',data:payload});toast('来源已保存，未开始远程调查');go('/manage/sources');
   });
  };
 }else{
  const b=await api(`${base}/batches/${id}`),offset=Math.max(0,Number(params.get('offset')||0)),q=params.get('q')||'',r=await api(`${base}/batches/${id}/candidates?`+new URLSearchParams({offset,q,limit:50}));
  if(!drafts.has(id))drafts.set(id,new Set(b.suggested_ids||r.items.filter(g=>g.suggested).map(g=>g.id)));
  const selected=drafts.get(id);
  body=`<a class="back-link" data-nav href="/manage/source-imports">${icon('back','sm')}返回来源资产</a>`+
    heading('研究批次',b.filename,`${tag(stateLabel[b.status]||b.status,b.status==='COMMITTED'?'green':b.status==='INVALID'?'red':'blue')}${b.status==='COMMITTED'?feedbackLink(id):''}`)+stats(b)+
    (b.error?`<div class="note danger">${icon('info')}<div><strong>文件未能完整读取</strong><p>${e(b.error)}</p>${fileLink(id,'upload/'+b.filename,'下载保留的原包')}</div></div>`:'')+
    (b.receipt?`<section class="scout-receipt"><div>${icon('checkcircle')}<strong>本批接收已保存</strong><span>${b.receipt.received} 个接收为候选 · ${b.receipt.conflicts} 个冲突 · ${b.receipt.not_selected} 个未接收</span></div><button id="show-receipt" class="text-btn">接收回执</button></section>`:'')+
    `<div class="table-controls"><div class="row gap8">${b.can_receive?'<button id="select-recommended" class="btn">按工具意见选择</button><button id="clear-selections" class="text-btn">清空选择</button>':'<span class="small muted">已接收候选可按需批准为来源</span>'}</div><form id="scout-search" class="mini-search">${icon('search','sm')}<input name="q" value="${e(q)}" aria-label="搜索研究候选" placeholder="搜索机构或入口"><button class="text-btn" type="submit">搜索</button></form></div>`+
    `<div class="work-table-wrap"><table class="work-table scout-table"><thead><tr>${b.can_receive?'<th class="scout-select"><input id="select-page" type="checkbox" aria-label="选择本页"></th>':''}<th>候选来源</th><th>主入口</th><th>外部意见</th><th>系统记录</th><th></th></tr></thead><tbody>${r.items.map(g=>`<tr>${b.can_receive?`<td class="scout-select"><input class="scout-selected" type="checkbox" data-id="${e(g.id)}" aria-label="接收${e(g.name)}" ${selected.has(g.id)?'checked':''}></td>`:''}<td><a class="record-title" data-nav href="/manage/source-imports/${e(id)}/candidate/${e(g.id)}">${e(g.name)}</a><span class="meta">${e(g.namespace)} · ${g.version_count} 条观察</span></td><td><span class="scout-url">${e(g.external_decision?.primary_seed||g.seed_urls[0]||'入口待确定')}</span>${g.seed_urls.length>1?'<span class="meta">多个入口</span>':''}</td><td>${tag(opinion[g.external_decision?.decision]||'待查看',g.external_decision?.decision==='PROPOSE_STAGING'?'blue':'')}</td><td>${tag(g.binding_current?'已关联来源':g.conflict?'批次内容冲突':stateLabel[g.state],g.binding_current?'green':g.conflict?'red':'')}${g.blocking&&!g.conflict?'<span class="meta">入口或身份待明确</span>':''}</td><td><a class="text-btn" data-nav href="/manage/source-imports/${e(id)}/candidate/${e(g.id)}">查看</a></td></tr>`).join('')}</tbody></table>${!r.items.length?empty('没有匹配的候选'):''}</div>`+
    pagination(offset,r.total,50,x=>`/manage/source-imports/${id}?`+new URLSearchParams({offset:x,q}))+
    (b.can_receive?`<div class="scout-actions"><div><strong id="selected-count">已选 ${selected.size} 个候选</strong><p class="small muted">接收研究资产，不批准来源，不开始调查。</p></div><button id="receive-scout" class="btn primary">接收所选候选</button></div>`:'')+
    `<details class="manage-panel mt24"><summary>批次原件与记录</summary><div class="mt16">${fileLink(id,'upload/'+b.filename,'下载上传原包')}</div><dl class="scout-record"><div><dt>提交时间</dt><dd>${e(time(b.created_at))}</dd></div><div><dt>原包 SHA-256</dt><dd class="code-detail">${e(b.package_sha256)}</dd></div></dl></details>`;
  after=()=>{
   const count=()=>{if($('#selected-count'))$('#selected-count').textContent=`已选 ${selected.size} 个候选`;};
   bind('#scout-search','submit',(_,f)=>go(`/manage/source-imports/${id}?`+new URLSearchParams({q:new FormData(f).get('q')})));
   $$('.scout-selected').forEach(el=>el.addEventListener('change',()=>{el.checked?selected.add(el.dataset.id):selected.delete(el.dataset.id);count();}));
   $('#select-page')?.addEventListener('change',ev=>{$$('.scout-selected').forEach(el=>{el.checked=ev.target.checked;el.checked?selected.add(el.dataset.id):selected.delete(el.dataset.id);});count();});
   bind('#clear-selections','click',()=>{selected.clear();$$('.scout-selected').forEach(el=>el.checked=false);count();});
   bind('#select-recommended','click',()=>{selected.clear();(b.suggested_ids||[]).forEach(x=>selected.add(x));$$('.scout-selected').forEach(el=>el.checked=selected.has(el.dataset.id));count();});
   bind('#receive-scout','click',async()=>{
    const key='receive-'+id;const data={preview_hash:b.preview_hash,selected_ids:[...selected],request_key:key};
    try{await api(`${base}/batches/${id}/receive`,{method:'POST',data});}
    catch(err){if(err.network){try{await api(`${base}/batches/${id}/receipt`);}catch{throw new Error('未取得接收回执；请重新打开本批次查看，不必重新上传');}}else throw err;}
    go('/manage/source-imports/'+id);toast('接收记录已保存');
   });
   bind('#show-receipt','click',()=>modal('系统接收回执',`<div class="kv"><span>接收候选</span><strong>${b.receipt.received}</strong></div><div class="kv"><span>来源登记</span><strong>0</strong></div><div class="kv"><span>新建调查</span><strong>0</strong></div><p class="tiny muted code-detail">${e(b.receipt.transaction_id)}</p>${feedbackLink(id)}`,null));
  };
 }
 return {body,after};
}
