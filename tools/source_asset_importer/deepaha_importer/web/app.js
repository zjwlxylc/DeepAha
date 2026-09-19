'use strict';
const $=id=>document.getElementById(id);
const state={session:null,selected:null,detail:null,tab:'decision',uploads:[],catalog:null,job:null,loadingDetail:0,requesting:false,libraryJob:null,libraryBusy:false};
let token=location.hash.slice(1)||sessionStorage.getItem('deepaha-local-session')||'';
if(location.hash){sessionStorage.setItem('deepaha-local-session',token);history.replaceState(null,'',location.pathname);}
const labels={SCORE_ARITHMETIC_MISMATCH:['评分加总不一致','保留原评分和计算值，不用分数替代来源真实性。'],MISSING_BRIEF_EVIDENCE_REFERENCE:['采集建议缺少所引证据','选定批次和状态中未找到这项引用，需要补齐原件或明确范围。'],MISSING_EVIDENCE_REFERENCE:['来源证据引用未闭合','不能用一段总结代替丢失的研究证据。'],MULTIPLE_SEEDS:['有多个入口，需要区分用途','明确主入口，其他地址保留为关联线索。不要把不同栏目强行合并。'],SEED_CHANGED_ACROSS_VERSIONS:['历史入口发生变化','查看各版本，确认是迁移、栏目变化还是错误关联。'],INVALID_SEED:['尚无可直接使用的公开入口','先暂缓；模板地址、公众号描述或空值不能直接作为采集入口。'],SEED_NORMALIZATION_PROPOSAL:['入口格式可规范化','原文仍保留，仅在比较键中去除已知跟踪参数或说明文字。'],FIRST_SEEN_CHANGED:['首次发现时间有不同申报','不使用最近一次复查时间覆盖真实首次发现时间。'],BRIEF_NOT_IN_SELECTED_HANDOFFS:['缺少对应采集建议','原件中未找到这个来源的采集建议。'],SYSTEM_MAPPING_UNVERIFIED:['系统ID尚未核实','外部研究者填写的系统ID不能替代DeepAha真实回执。'],RUN_CONTENT_CONFLICT:['相同批次标识对应不同内容','这不是普通历史版本，需先确认正确批次身份。'],MISSING_CANDIDATE_KEY:['候选身份缺失','补齐明确的候选键后重新检查。'],ATTACHMENT_SIZE_CLAIM_MISMATCH:['附件大小申报与字节不一致','哈希可能能定位到原件，但错误的大小记录仍须保留并解释。'],ATTACHMENT_DECLARED_HASH_NOT_IN_SELECTED_PACKAGE:['附件原件未在本批找到','仅有哈希申报不代表已取得原件。'],ATTACHMENT_PATH_ONLY_UNVERIFIED:['只有附件路径，未完成字节核验','不会按路径猜测另一份同名文件。']};
const decisionLabels={PROPOSE_STAGING:'建议接收为候选',DEFER:'暂缓，待补证',REJECT:'不采用',PENDING:'待处理'};
function el(tag,cls,text){const x=document.createElement(tag);if(cls)x.className=cls;if(text!==undefined)x.textContent=String(text);return x;}
function append(node,...children){children.filter(x=>x!==null&&x!==undefined).forEach(x=>node.append(typeof x==='string'?document.createTextNode(x):x));return node;}
function readable(value){return value==null?'未说明':typeof value==='string'?value:JSON.stringify(value,null,2);}
function size(n){return n>1048576?(n/1048576).toFixed(1)+' MiB':(n/1024).toFixed(1)+' KiB';}
function displayTime(t){try{return new Date(t).toLocaleString('zh-CN',{hour12:false});}catch{return t||'未说明';}}
function notice(message,error=false){$('notice').hidden=false;$('notice').className='notice'+(error?' error':'');$('notice').textContent=message;}
async function api(path,body,raw=false){
 const opts={headers:{'X-DeepAha-Session':token}};
 if(body!==undefined){opts.method='POST';opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body);}
 opts.signal=AbortSignal.timeout(15000);
 const response=await fetch(path,opts);
 if(!response.ok){let result;try{result=await response.json();}catch{result={};}const e=new Error(result.error?.message||'请求未完成，请重新打开工作台检查。');e.code=result.error?.code;throw e;}
 return raw?response.blob():response.json();
}
function action(fn){return async event=>{try{await fn(event);}catch(e){notice(e.message,true);if($('library-dialog').open)$('library-status').textContent=e.message;}};}
function busy(title,text,cancellable=false){$('busy').hidden=false;$('busy-title').textContent=title;$('busy-text').textContent=text||'原件和已保存意见不会被覆盖。';$('cancel-job').hidden=!cancellable;}
function libraryBusy(value){
 state.libraryBusy=value;$('library-progress').hidden=!value;
 ['library-list-button','library-folder','save-config','codex-path','codex-profile','codex-model','codex-timeout','codex-network','library-local-files','library-local-folder'].forEach(id=>$(id).disabled=value);
 $('library-fetch-button').disabled=value||!state.catalog||!$('library-files').querySelector('input:checked');
 $('library-cancel').disabled=false;
}
async function job(path,body,title,cancellable=false){
 if(state.requesting||state.job)throw new Error('已有操作正在进行，请等待或先取消。');
 state.requesting=true;const inLibrary=path.startsWith('/api/library/');let j;
 const started=Date.now(),deadline=started+(inLibrary?(path.endsWith('/list')?120000:660000):600000);
 try{
  if(inLibrary){libraryBusy(true);$('library-progress-title').textContent=title;$('library-status').textContent='正在检查，不代表连接已成功。';$('library-diagnostic').hidden=true;}
  else busy(title,'正在处理',cancellable);
  j=await api(path,body);state.job=j.job_id;if(inLibrary)state.libraryJob=j.job_id;
  while(Date.now()<deadline){
   await new Promise(r=>setTimeout(r,350));
   const result=await api('/api/job?id='+encodeURIComponent(j.job_id));
   const seconds=Math.round((Date.now()-started)/1000);
   if(inLibrary){$('library-progress-text').textContent=result.progress||'等待Codex响应';$('library-elapsed').textContent=`已等待 ${seconds} 秒 · 可以随时取消`;$('library-diagnostic').hidden=!result.diagnostic;}
   else $('busy-text').textContent=result.progress||'正在处理';
   if(result.status==='DONE')return result.result;
   if(['ERROR','CANCELLED'].includes(result.status)){const e=new Error(result.error?.message||'操作未完成');e.code=result.error?.code;throw e;}
  }
  throw new Error('等待已超过本次上限，已请求停止。可以下载连接诊断，或选择已下载文件继续。');
 }catch(e){
  if(j){try{await api('/api/cancel',{job_id:j.job_id});}catch{}}
  throw e;
 }finally{state.job=null;state.requesting=false;$('busy').hidden=true;if(inLibrary)libraryBusy(false);}
}

function pane(name){
 if(name!=='intake'&&!state.session){notice('先选择研究包并完成一次检查。');name='intake';}
 document.querySelectorAll('.pane').forEach(p=>p.hidden=p.id!=='pane-'+name);
 document.querySelectorAll('.step').forEach(p=>p.classList.toggle('current',p.dataset.pane===name));
 if(name==='export')renderExport();if(name==='feedback')renderFeedback();
}
async function refreshRecent(){const sessions=await api('/api/sessions');$('recent-list').replaceChildren();sessions.slice(0,5).forEach(s=>{const b=el('button','',displayTime(s.created_at));b.title='打开这次审核，不重新读取或覆盖原件';b.onclick=action(()=>loadSession(s.id));$('recent-list').append(b);});return sessions;}
async function loadSession(id){state.session=await api('/api/session?id='+encodeURIComponent(id));state.selected=null;state.detail=null;document.body.classList.remove('has-detail');renderReview();pane('review');await refreshRecent();}
async function refreshSession(keep=true){const selected=state.selected;state.session=await api('/api/session?id='+state.session.id);renderReview();if(keep&&selected)await loadSource(selected,false);}
async function uploadFiles(files){
 if(!files.length)return;
 busy('正在读取所选文件','只传到本机工作台，不发送到外部服务器。');
 try{for(let i=0;i<files.length;i++){const file=files[i];if(file.size>100*1048576)throw new Error('文件 '+file.name+' 超过100MiB，请分包处理。');$('busy-text').textContent=`读取第 ${i+1}/${files.length} 个文件：${file.name}`;
 const res=await fetch('/api/upload',{method:'POST',headers:{'X-DeepAha-Session':token,'X-File-Name':encodeURIComponent(file.webkitRelativePath||file.name)},body:file});
 const out=await res.json();if(!res.ok)throw new Error(out.error?.message||'文件传输失败');state.uploads.push(out);renderUploads();}
 notice(`已选择 ${state.uploads.length} 个文件。点击“开始检查”，不会直接写入数据库。`);
 }finally{$('busy').hidden=true;}
}
function renderUploads(){const list=$('uploads-list');list.replaceChildren();state.uploads.forEach((f,i)=>{const row=el('div','upload-item');const remove=el('button','','×');remove.setAttribute('aria-label','移除 '+f.name);remove.onclick=()=>{state.uploads.splice(i,1);renderUploads();};append(row,el('span','filename',f.name),el('span','muted',size(f.size_bytes)),remove);list.append(row);});$('analyze').disabled=!state.uploads.length;}
function metric(name,value,note){return append(el('article','metric'),el('span','',name),el('strong','',value),el('small','',note));}
function renderReview(){
 if(!state.session)return;const a=state.session.analysis,s=a.summary,d=state.session.decisions;
 $('metrics').replaceChildren(metric('来源审核对象',s.candidate_groups,`${s.batches} 个批次 · ${s.source_versions} 条原始记录`),metric('待我处理',s.candidate_groups-Object.keys(d).length,'已保存意见可撤销，历史仍保留'),metric('重复身份观察',s.repeated_identity_versions,'归并展示，不删除历史内容'),metric('需先补充',s.blocked_sources,'身份或入口未满足交接前提'));
 $('review-subtitle').textContent=`已保存 ${state.session.revision} 次操作 · ${s.brief_versions} 份采集建议记录 · ${s.attachment_files} 份附件原件（字节盘点，不等于读懂内容）`;
 $('batch-warning').hidden=!s.timeline_anomalies;
 if(s.timeline_anomalies)$('batch-warning').textContent=`${s.timeline_anomalies} 份批次文件存在开始与完成时间相同的申报。文件链可核验，但这些时间不能证明独立联网研究次数；不会因此提高来源可信度。`;
 renderList();
}
function renderList(){
 if(!state.session)return;const term=$('search').value.trim().toLowerCase(),filter=$('filter').value,producer=$('producer').value,d=state.session.decisions;
 const rows=state.session.analysis.sources.filter(g=>{
  if(producer!=='all'&&g.namespace!==producer)return false;
  if(term&&!`${readable(g.name)} ${readable(g.institution)} ${g.seed_urls.join(' ')}`.toLowerCase().includes(term))return false;
  return filter==='all'||filter==='pending'&&!d[g.id]||filter==='done'&&d[g.id]||filter==='issues'&&g.review_needed||filter==='blocked'&&g.blocking;
 });
 $('result-count').textContent=rows.length+' 个';$('source-list').replaceChildren();
 rows.forEach(g=>{const b=el('button','source-row'+(state.selected===g.id?' selected':''));b.setAttribute('aria-pressed',String(state.selected===g.id));const meta=el('div','row-meta');append(meta,el('span','tag',g.namespace==='wb-scout'?'WB Scout':g.namespace==='chatgpt-scout'?'GPT Scout':g.namespace),el('span','',`${g.repeat_versions+1} 条观察`));if(d[g.id])meta.append(el('span','tag done',decisionLabels[d[g.id].decision]));else if(g.blocking)meta.append(el('span','tag danger','需先补充'));else if(g.review_needed)meta.append(el('span','tag warning','有疑点'));else meta.append(el('span','tag','结构检查无阻断'));
 append(b,meta,el('h3','',readable(g.name)),el('p','row-note',g.issue_codes.length?(labels[g.issue_codes[0]]?.[0]||'存在待核对项目'):'所有版本保留，正式来源身份尚待系统确认'));b.onclick=action(()=>loadSource(g.id));$('source-list').append(b);});
 if(!rows.length){
  const complete=Object.keys(d).length===state.session.analysis.summary.candidate_groups;
  const empty=append(el('div','empty-detail'),el('h2','',complete&&filter==='pending'?'本次来源都已处理':'没有符合当前筛选的来源'),el('p','',complete?'审核意见已保存，来源并未消失；可查看已处理项或导出交接包。':'调整搜索或筛选，不会删除任何来源。'));
  const view=el('button','outline','查看已处理来源');view.onclick=()=>{$('filter').value='done';$('search').value='';$('producer').value='all';renderList();};
  const next=el('button','primary','前往导出交接包');next.onclick=()=>pane('export');
  append(empty,append(el('div','button-row'),view,next));$('source-list').append(empty);
 }
}
async function loadSource(id,scroll=true){
 state.selected=id;renderList();const serial=++state.loadingDetail;const result=await api('/api/source?id='+state.session.id+'&source='+id);if(serial!==state.loadingDetail)return;
 state.detail=result;document.body.classList.add('has-detail');renderDetail();if(scroll&&innerWidth<=680)$('source-detail').scrollIntoView({behavior:'smooth',block:'start'});
}
function details(title,data){return append(el('details',''),el('summary','',title),el('pre','',readable(data)));}
function link(url,label){try{const u=new URL(url);if(!['https:','http:'].includes(u.protocol))return el('span','muted',label||url);const a=el('a','',label||url);a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;}catch{return el('span','muted',label||url);}}
function renderDetail(){
 const r=state.detail;if(!r)return;const g=r.source,host=$('source-detail');host.replaceChildren();
 const back=el('button','mobile-back outline','← 返回来源列表');back.onclick=()=>{document.body.classList.remove('has-detail');state.selected=null;renderList();$('pane-review').scrollIntoView({block:'start'});};host.append(back);
 const header=el('div','detail-header');append(header,el('span','tag',g.namespace==='wb-scout'?'WB Scout':'GPT Scout'),el('h2','',readable(g.name)),el('p','muted','机构申报：'+readable(g.institution)));host.append(header);
 const tabs=el('div','tabs');[['decision','处理意见'],['evidence','依据与附件'],['versions','版本记录']].forEach(([value,label])=>{const b=el('button',state.tab===value?'active':'',label);b.onclick=()=>{state.tab=value;renderDetail();};tabs.append(b);});host.append(tabs);
 const body=el('div','detail-section');host.append(body);
 if(state.tab==='decision'){
  append(body,el('h3','','本次需核对'),el('div','callout info','这里只保存本地审核意见。即使建议接收，也不代表来源已获批准或可立即采集。'));
  const issues=el('div','issues'),seen=new Set();r.issues.forEach(i=>{const key=i.code+JSON.stringify(i.reference||i.detail||'');if(seen.has(key))return;seen.add(key);const [title,explanation]=labels[i.code]||['需要进一步核对','请展开检查记录查看具体原因。'];const card=append(el('article','issue-card'),el('strong','',title),el('p','',explanation));card.append(details('查看具体记录',i));issues.append(card);});
  if(!seen.size)issues.append(append(el('article','issue-card'),el('strong','','结构检查未发现阻断'),el('p','','这不是官方真实性或时效性验证；建议接收也仅进入候选审核。')));
  r.relations.forEach(x=>issues.append(append(el('article','issue-card'),el('strong','',x.kind==='SAME_ENDPOINT'?'与另一档案使用相同入口':'与另一档案可能有关联'),el('p','',x.left===g.id?x.right_name:x.left_name),el('p','',x.reason),el('small','muted','当前仍为独立档案，没有自动合并。'))));body.append(issues);
  const form=el('form','decision-form');append(form,el('h3','','保存我的处理意见'));
  const grid=el('div','form-grid'),actor=el('input'),decision=el('select'),reason=el('textarea'),seed=el('select');actor.id='review-actor';actor.value=localStorage.getItem('deepaha-review-actor')||r.decision?.actor||'';actor.required=true;actor.maxLength=120;actor.placeholder='你的姓名或工作标识';reason.id='review-reason';reason.required=true;reason.maxLength=4000;reason.placeholder='例如：先接收为候选；正式启用前需核实年度入口与附件。';reason.value=r.decision?.reason||'';
  [['PROPOSE_STAGING','建议接收为候选（不批准采集）'],['DEFER','暂缓，待补证'],['REJECT','不采用']].forEach(([v,t])=>{const o=el('option','',t);o.value=v;decision.append(o);});decision.id='review-decision';decision.value=r.decision?.decision||(g.blocking?'DEFER':'PROPOSE_STAGING');
  const actorLabel=append(el('label','','操作者'),actor),decisionLabel=append(el('label','','处理意见'),decision),reasonLabel=append(el('label','full','原因（会进入审核记录）'),reason);append(grid,actorLabel,decisionLabel);
  if(g.seed_urls.length>1){const no=el('option','','请选择一个主入口');no.value='';seed.append(no);g.seed_urls.forEach(u=>{const o=el('option','',u);o.value=u;seed.append(o);});seed.value=r.decision?.primary_seed||'';seed.id='review-primary';grid.append(append(el('label','full','主入口（其他地址继续保留）'),seed));}
  append(grid,reasonLabel);form.append(grid);
  const ack=el('input');ack.type='checkbox';ack.id='review-ack';ack.checked=!!r.decision?.acknowledged_issues;
  if(g.review_needed)form.append(append(el('label','checkbox'),ack,el('span','','我已看过上述疑点；若建议接收，仅作为待确认候选，不代表批准采集。')));
  const save=el('button','primary','保存意见');save.type='submit';const undo=el('button','outline','撤销这条意见');undo.type='button';undo.disabled=!r.decision;undo.onclick=action(async()=>{await api('/api/undo',{session_id:state.session.id,source_id:g.id,revision:state.session.revision,reason:'操作者撤销本次意见，恢复待处理',actor:actor.value});await refreshSession();notice('已恢复为待处理。原意见和撤销记录都已保留。');});append(form,append(el('div','button-row'),save,undo));
  if(g.blocking)form.append(el('p','muted tiny','此档案有阻断问题，只能暂缓或不采用。补齐正确原件后新建审核，不覆盖旧档案。'));
  form.onsubmit=action(async e=>{e.preventDefault();save.disabled=true;try{await api('/api/decision',{session_id:state.session.id,source_id:g.id,revision:state.session.revision,decision:decision.value,reason:reason.value,actor:actor.value,acknowledge_issues:ack.checked,primary_seed:g.seed_urls.length>1?seed.value:null});localStorage.setItem('deepaha-review-actor',actor.value);await refreshSession();notice('处理意见已保存到本地；没有提交DeepAha。');}finally{save.disabled=false;}});body.append(form);
 }else if(state.tab==='evidence'){
  body.append(el('h3','','公开入口（研究者申报）'));g.seed_urls.forEach(u=>body.append(append(el('div','source-entry'),link(u))));if(!g.seed_urls.length)body.append(el('p','muted','尚无可直接使用的公开HTTP(S)入口。'));body.append(details('原始入口字段',g.seed_original));
  body.append(el('h3','',`关联证据记录 · ${g.evidence_versions.length}`));g.evidence_versions.forEach(e=>{const v=e.payload,entry=el('article','source-entry');append(entry,el('strong','',v.title||e.key),el('small','',e.run_key));const u=v.url||v.public_url;if(u)entry.append(append(el('p',''),link(u)));entry.append(details('原始证据字段与文件定位',e));body.append(entry);});
  if(r.attachments?.length){body.append(el('h3','','附件字节核对'));r.attachments.forEach(a=>body.append(append(el('article','source-entry'),el('strong','',a.status==='HASH_AND_SIZE_MATCH'?'已找到哈希一致原件（未核实内容）':'附件申报需要核对'),el('p','muted',a.evidence_key),details('路径、大小与哈希',a))));}
  body.append(el('h3','',`采集建议版本 · ${g.brief_versions.length}`));g.brief_versions.forEach(b=>body.append(details(b.run_key+' · '+b.key,b)));
 }else{
  body.append(el('div','callout info','按文件申报的时间选择当前展示版本，不代表最新记录一定正确。所有原文、旧值和文件哈希都保留。'));
  if(g.field_history)body.append(details('发生变化的字段',g.field_history));g.versions.slice().reverse().forEach((v,i)=>body.append(details((i===0?'当前展示 · ':'历史观察 · ')+v.run_key,v)));
  body.append(details('候选身份与全部元数据',{namespace:g.namespace,candidate_key:g.candidate_key,authority_claim:g.authority_claim,authority_validation:g.authority_validation,system_source_id:g.system_source_id}));
 }
}
function renderExport(){
 if(!state.session)return;const s=state.session,counts=Object.values(s.decisions).reduce((a,x)=>(a[x.decision]=(a[x.decision]||0)+1,a),{}),pending=s.analysis.summary.candidate_groups-Object.keys(s.decisions).length;
 $('export-summary').replaceChildren(el('h2','',pending?`还有 ${pending} 个对象待处理`:'这次审核意见已填写完整'),el('p','',`建议接收 ${counts.PROPOSE_STAGING||0} · 暂缓 ${counts.DEFER||0} · 不采用 ${counts.REJECT||0}。导出包含原件、全部历史、疑点、审核日志和校验清单。`));
 $('export-button').textContent=pending?'导出审核备份（含待处理项）':'生成候选交接包';$('exports-list').replaceChildren();s.export_history.slice().reverse().forEach(e=>{const row=el('div','export-line');const info=append(el('div',''),el('strong','',`审核版本 r${e.review_revision} · ${e.review_revision===s.revision?'当前版本':'旧版本，不代表当前意见'}`),el('small','',e.filename));const button=el('button','outline','下载该版本');button.onclick=action(()=>download(e.filename));append(row,info,button);$('exports-list').append(row);});
}
async function download(name){const blob=await api('/api/download?file='+encodeURIComponent(name),undefined,true);const u=URL.createObjectURL(blob),a=el('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),30000);}
function renderFeedback(){if(!state.session)return;$('feedback-list').replaceChildren();const list=state.session.feedback;if(!list.length){$('feedback-list').append(el('p','muted','尚未读取系统反馈。没有反馈不等于采集失败，也不能按0条成功来评分。'));return;}list.forEach(f=>{const card=el('article','source-entry');append(card,el('strong','','已读取声明 · 发行方尚未认证'),el('p','muted',`${f.payload.environment} · 包关联：${f.verification.bundle_binding==='MATCH'?'与本地导出对应':'尚未匹配'} · 不修改正式状态`),details('查看反馈与核验边界',f));$('feedback-list').append(card);});}
async function openLibrary(){if(state.job||state.requesting)throw new Error('请先完成当前操作。');const c=await api('/api/config');$('codex-path').value=c.codex.executable;$('codex-profile').value=c.codex.profile;$('codex-model').value=c.codex.model;$('codex-timeout').value=c.codex.timeout_seconds;$('codex-network').checked=c.codex.allow_network_downloads;$('library-dialog').showModal();}
$('choose-files').onclick=()=>$('file-input').click();$('choose-folder').onclick=()=>$('folder-input').click();$('file-input').onchange=action(e=>uploadFiles([...e.target.files]));$('folder-input').onchange=action(e=>uploadFiles([...e.target.files]));
$('dropzone').ondragover=e=>{e.preventDefault();$('dropzone').classList.add('dragover');};$('dropzone').ondragleave=()=>$('dropzone').classList.remove('dragover');$('dropzone').ondrop=action(async e=>{e.preventDefault();$('dropzone').classList.remove('dragover');await uploadFiles([...e.dataTransfer.files]);});
$('analyze').onclick=action(async()=>{$('analyze').disabled=true;try{const r=await job('/api/analyze',{uploads:state.uploads.map(x=>x.id),namespace:$('namespace').value},'正在核对原件、批次和来源');await loadSession(r.session_id);notice('批量检查完成。重复身份已归并展示，所有原件和版本仍然保留。');}finally{$('analyze').disabled=!state.uploads.length;}});
$('search').oninput=renderList;$('filter').onchange=renderList;$('producer').onchange=renderList;
document.querySelectorAll('[data-pane]').forEach(b=>b.onclick=()=>pane(b.dataset.pane));
$('new-review').onclick=()=>{state.uploads=[];renderUploads();pane('intake');notice('开始新的审核，不会覆盖之前的记录。');};
$('export-button').onclick=action(async()=>{const r=await job('/api/export',{session_id:state.session.id,revision:state.session.revision},'正在核验原件并生成交接包');await refreshSession(false);renderExport();await download(r.filename);notice('审核包已生成，尚未提交DeepAha。旧版导出仍保留。');});
$('feedback-choose').onclick=()=>$('feedback-input').click();$('feedback-input').onchange=action(async e=>{if(!e.target.files.length)return;const count=state.uploads.length;await uploadFiles([e.target.files[0]]);const u=state.uploads[count];if(u){await api('/api/feedback',{session_id:state.session.id,upload_id:u.id,revision:state.session.revision});await refreshSession(false);renderFeedback();notice('反馈结构已检查，仅保存声明。未经发行方认证，不更新正式系统状态。');}});
$('library-open').onclick=action(openLibrary);$('library-close').onclick=()=>{if(state.libraryBusy){$('library-status').textContent='请先取消本次获取，停止后再关闭。';$('library-cancel').focus();}else $('library-dialog').close();};
$('library-dialog').addEventListener('cancel',e=>{if(state.libraryBusy){e.preventDefault();cancelLibrary();}});
$('library-local-files').onclick=()=>{$('library-dialog').close();pane('intake');$('file-input').click();};
$('library-local-folder').onclick=()=>{$('library-dialog').close();pane('intake');$('folder-input').click();};
async function cancelLibrary(){
 if(!state.job)return;
 $('library-cancel').disabled=true;
 try{await api('/api/cancel',{job_id:state.job});$('library-progress-text').textContent='已请求取消，正在关闭本次Codex进程；已有审核不会丢失。';}
 catch(e){$('library-cancel').disabled=false;$('library-status').textContent=e.message;}
}
$('library-cancel').onclick=action(cancelLibrary);
$('library-diagnostic').onclick=action(async()=>{if(!state.libraryJob)return;const blob=await api('/api/library/diagnostic?job_id='+encodeURIComponent(state.libraryJob),undefined,true);saveBlob(blob,'DeepAha_Library_Diagnostic.json');});
function saveBlob(blob,name){const u=URL.createObjectURL(blob),a=el('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),30000);}

$('save-config').onclick=action(async()=>{await api('/api/config',{codex:{executable:$('codex-path').value,profile:$('codex-profile').value,model:$('codex-model').value,timeout_seconds:Number($('codex-timeout').value),allow_network_downloads:$('codex-network').checked}});state.catalog=null;$('library-files').replaceChildren();$('library-fetch-button').disabled=true;$('library-status').textContent='设置已保存在本机。旧目录清单已清空，请重新检查连接；不会修改Codex权限。';});
$('library-list-button').onclick=action(async()=>{state.catalog=null;$('library-files').replaceChildren();$('library-fetch-button').disabled=true;const cat=await job('/api/library/list',{folder_path:$('library-folder').value},'检查Codex并连接资料库',true);state.catalog=cat;$('library-status').textContent=`已实际读到 ${cat.files.length} 个文件的目录记录，尚未取回原件。${cat.listing_complete?'本次清单完整。':'仅列出部分文件。'}`;cat.files.forEach((f,i)=>{const check=el('input');check.type='checkbox';check.value=i;check.onchange=()=>{$('library-fetch-button').disabled=!$('library-files').querySelector('input:checked');};const text=append(el('div',''),el('strong','',f.name),el('div','muted tiny',(f.size_bytes?size(f.size_bytes):'大小未提供')+' · 版本 '+(f.version||'未提供')));$('library-files').append(append(el('label',''),check,text));});});
$('library-fetch-button').onclick=action(async()=>{const indexes=[...$('library-files').querySelectorAll('input:checked')].map(x=>Number(x.value));const r=await job('/api/library/fetch',{catalog_id:state.catalog.catalog_id,indexes},'正在取回所选原件',true);state.uploads.push(...r.uploads);renderUploads();$('library-dialog').close();pane('intake');notice(`已取回 ${r.uploads.length} 个原件，尚未导入。${r.failures.length?'有 '+r.failures.length+' 个文件未成功：'+r.failures.map(x=>x.name+'：'+x.message).join('；'):''}${r.cancelled?'本次获取已取消；已取回文件保留。':''}`,!!r.failures.length);});
$('cancel-job').onclick=action(async()=>{if(state.job)await api('/api/cancel',{job_id:state.job});$('busy-text').textContent='已请求取消；已取回文件保留。';});
$('legacy-open').onclick=action(async()=>{const r=await api('/api/legacy',{});notice(r.message);});
(async()=>{try{const recent=await refreshRecent();if(recent.length)await loadSession(recent[0].id);}catch(e){notice(e.message,true);}})();
