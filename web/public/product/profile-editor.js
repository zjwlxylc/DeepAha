import {$,e,api,bind,modal,toast} from './core.js';
import {changedFields} from './experience-core.js';

/** Only controls actually changed by the user are submitted. Missing fields are never cleared. */
export function readProfileForm(form){
 const result={},data=new FormData(form);
 const arrayFields=new Set(['cities','career_directions','interests','goals','skills','constraints','certificates','language_certificates']);
 const numbers=new Set(['graduation_year','team_size','work_experience_years']);
 const multi=new Set(['opportunity_types','deadline_reminder_days']);
 for(const control of form.elements){
  const k=control.name;if(!k||control.disabled)continue;
  if(multi.has(k)){result[k]=data.getAll(k).map(v=>k==='deadline_reminder_days'?Number(v):v);continue;}
  if(control.type==='checkbox'){result[k]=control.checked;continue;}
  const value=String(data.get(k)??'');
  result[k]=arrayFields.has(k)?value.split(/[，,、\n]/).map(x=>x.trim()).filter(Boolean):numbers.has(k)?(value===''?null:Number(value)):value;
 }
 return result;
}
export function bindProfilePatch(form,snapshot,focus){
 let version=snapshot.version,initial=readProfileForm(form),saved=JSON.stringify(initial);
 const message=document.createElement('p');message.className='profile-save-state span2';message.setAttribute('role','status');form.append(message);
 const showDirty=()=>{message.textContent=JSON.stringify(readProfileForm(form))===saved?'':'有尚未保存的修改';};
 form.addEventListener('input',showDirty);form.addEventListener('change',showDirty);
 const save=async(changes,v)=>{
  const r=await api('/api/me/profile',{method:'PATCH',data:{expected_version:v,changes}});
  version=r.version;initial=readProfileForm(form);saved=JSON.stringify(initial);message.textContent='关注方向已保存';toast('关注方向与通知设置已保存');
 };
 bind('#profile-form','submit',async()=>{
  const changes=changedFields(initial,readProfileForm(form));
  if(!Object.keys(changes).length){toast('没有需要保存的修改');return;}
  try{await save(changes,version);}catch(err){
   if(err.status!==409)throw err;
   message.textContent='资料已在别处更新；本页输入仍保留。';
   const latest=await api('/api/me/profile-state');
   const rows=Object.keys(changes).map(k=>{
    const c=form.elements.namedItem(k),label=c?.closest?.('.form-field')?.querySelector('label')?.textContent||k;
    const text=v=>Array.isArray(v)?v.join('、'):typeof v==='boolean'?(v?'开启':'关闭'):v??'未填写';
    return `<tr><th>${e(label)}</th><td>${e(text(latest.profile[k]))}</td><td>${e(text(changes[k]))}</td></tr>`;
   }).join('');
   modal('资料已在别处更新',`<p>核对以下差异后再保存。未在本页修改的资料继续保留最新内容。</p><div class="work-table-wrap mt16"><table class="work-table"><thead><tr><th>资料</th><th>当前保存值</th><th>本次编辑值</th></tr></thead><tbody>${rows}</tbody></table></div>`,async()=>{await save(changes,latest.version);},'保留本次编辑并保存');
  }
 });
 const target=typeof focus==='string'?form.elements.namedItem(focus):null;
 if(target?.focus){for(let p=target.parentElement;p&&p!==form;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;target.focus();target.scrollIntoView({block:'center'});}
}
