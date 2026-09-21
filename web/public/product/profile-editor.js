import {$,e,api,bind,modal,toast,state,registerLeaveGuard,go} from './core.js';
import {changedFields} from './experience-core.js';
import {arrangeProfile} from './profile-layout.js';
const drafts=new Map();
window.addEventListener('authchange',()=>drafts.clear());

export function readProfileForm(form){
 const result={},data=new FormData(form),arrayFields=new Set(['cities','career_directions','interests','goals','skills','constraints','certificates','language_certificates']),numbers=new Set(['graduation_year','team_size','work_experience_years']),multi=new Set(['opportunity_types','deadline_reminder_days']);
 for(const control of form.elements){
  const k=control.name;if(!k||control.disabled)continue;
  if(multi.has(k)){result[k]=data.getAll(k).map(v=>k==='deadline_reminder_days'?Number(v):v);continue;}
  if(control.type==='checkbox'){result[k]=control.checked;continue;}
  const value=String(data.get(k)??'');
  result[k]=arrayFields.has(k)?value.split(/[，,、\n]/).map(x=>x.trim()).filter(Boolean):numbers.has(k)?(value===''?null:Number(value)):value;
 }
 return result;
}
function applyValues(form,values){
 for(const control of form.elements){
  const k=control.name;if(!k||!(k in values))continue;const value=values[k];
  if(control.type==='checkbox')control.checked=Array.isArray(value)?value.map(String).includes(control.value):Boolean(value);
  else control.value=Array.isArray(value)?value.join('，'):value??'';
 }
 if('birth_date' in values){const [y='',m='',d='']=String(values.birth_date||'').split('-');form.querySelector('#birth-year').value=y;form.querySelector('#birth-month').value=m?String(Number(m)):'';form.querySelector('#birth-day').value=d?String(Number(d)):'';form.querySelector('#birth-year').dispatchEvent(new Event('input'));}
}
export function bindProfilePatch(form,snapshot,focus,back=''){
 const savebar=arrangeProfile(form),key=state.user?.username;
 let version=snapshot.version,initial=readProfileForm(form),saved=JSON.stringify(initial);
 const draft=drafts.get(key);if(draft){version=draft.version;initial=draft.initial;saved=JSON.stringify(initial);applyValues(form,draft.values);}
 const message=document.createElement('p');message.className='profile-save-state';message.setAttribute('role','status');savebar.prepend(message);
 const dirty=()=>JSON.stringify(readProfileForm(form))!==saved;
 const remember=()=>{if(dirty())drafts.set(key,{version,initial,values:readProfileForm(form)});else drafts.delete(key);message.textContent=dirty()?'有尚未保存的修改':'资料已保存';};
 form.addEventListener('input',remember);form.addEventListener('change',remember);
 const dispose=registerLeaveGuard(dirty,()=>drafts.delete(key));
 if(draft)message.textContent='已恢复本次浏览中的未保存修改';
 const save=async(changes,v)=>{
  const r=await api('/api/me/profile',{method:'PATCH',data:{expected_version:v,changes}});
  applyValues(form,r.profile);version=r.version;initial=readProfileForm(form);saved=JSON.stringify(initial);drafts.delete(key);message.textContent='关注方向已保存';toast('关注方向与通知设置已保存');
 };
 bind('#profile-form','submit',async()=>{
  const changes=changedFields(initial,readProfileForm(form));
  if(!Object.keys(changes).length){toast('没有需要保存的修改');return;}
  try{await save(changes,version);}catch(err){
   if(err.status!==409)throw err;
   message.textContent='资料已在别处更新；本页输入仍保留。';
   const latest=await api('/api/me/profile-state');
   const rows=Object.keys(changes).map(k=>{const c=form.elements.namedItem(k),label=c?.closest?.('.form-field')?.querySelector('label')?.textContent||k;const text=v=>Array.isArray(v)?v.join('、'):typeof v==='boolean'?(v?'开启':'关闭'):v??'未填写';return `<tr><th>${e(label)}</th><td>${e(text(latest.profile[k]))}</td><td>${e(text(changes[k]))}</td></tr>`;}).join('');
   modal('资料已在别处更新',`<p>核对差异后再保存。未修改的资料保留最新内容。</p><div class="work-table-wrap mt16"><table class="work-table"><thead><tr><th>资料</th><th>当前保存值</th><th>本次编辑值</th></tr></thead><tbody>${rows}</tbody></table></div>`,async()=>{await save(changes,latest.version);},'保留本次编辑并保存');
  }
 });
 if(back){const button=document.createElement('a');button.href=back;button.dataset.nav='';button.className='text-btn';button.textContent='返回机会';savebar.append(button);}
 const target=typeof focus==='string'?form.elements.namedItem(focus):null;
 if(target?.focus){for(let p=target.parentElement;p&&p!==form;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;requestAnimationFrame(()=>{target.focus();target.scrollIntoView({block:'center'});});}
 return dispose;
}
