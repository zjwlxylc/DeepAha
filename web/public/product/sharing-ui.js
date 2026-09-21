import {api,bind,e,has,modal,toast,go,registerLeaveGuard} from './core.js';
const input=(name,label,value,extra='')=>`<label class="form-field"><span>${label}</span><input name="${name}" value="${e(value)}" ${extra}></label>`;
const imageURL=id=>'/share-assets/'+encodeURIComponent(id);
export async function renderSharing(){
 if(!has('operator'))throw Object.assign(new Error('仅维护员可设置网站分享'),{status:403});
 const result=await api('/api/manage/sharing');const {diagnostics,...initial}=result;
 let saved={...initial},cover=initial.cover,square=initial.square,dirty=false;
 const body=`<div class="work-title"><div><h1>网站分享</h1><p>统一公开链接的封面、标题与描述。</p></div><a class="btn" href="/share" target="_blank" rel="noopener">打开实际分享页 ↗</a></div>
 <div class="sharing-layout"><form class="manage-panel share-config" id="share-config"><h2>分享样式</h2>
 ${input('origin','网站HTTPS域名',initial.origin,'required type="url" maxlength="300"')}
 ${input('title','分享标题',initial.title,'required maxlength="80"')}
 <label class="form-field"><span>分享描述</span><textarea name="description" required maxlength="220">${e(initial.description)}</textarea></label>
 <div class="share-uploads"><label class="cover-picker">横版封面 · 1200 × 630<span class="cover-select-label">选择横版图片</span><input class="cover-native-input" type="file" id="share-cover-file" accept="image/png,image/jpeg,image/webp"><span class="muted tiny">PNG / JPEG / WEBP，最多5MB</span></label><label class="cover-picker">微信缩略图 · 600 × 600<span class="cover-select-label">选择方形图片</span><input class="cover-native-input" type="file" id="share-square-file" accept="image/png,image/jpeg,image/webp"><span class="muted tiny">自动裁切；不要上传个人资料图片</span></label></div>
 <details class="mt24"><summary>微信专用分享配置</summary><div class="stack mt16"><label class="checkbox-field"><input name="wechat_enabled" type="checkbox" ${initial.wechat_enabled?'checked':''}>在微信中启用专用分享样式</label><p class="muted small">服务端凭据：${diagnostics.credentials_configured?'已配置':'尚未配置'}。密钥只在服务器环境变量中设置，不填写到网页中。</p>
 ${input('verification_name','域名验证文件名',initial.verification_name,'maxlength="120" placeholder="MP_verify_xxx.txt"')}
 ${input('verification_text','域名验证文件内容',initial.verification_text,'maxlength="256" autocomplete="off"')}
 <p class="muted tiny">需要在微信开发者后台完成账号权限、JS接口安全域名及接口IP白名单设置。已配置不等于真实微信验收通过。OG用于网页元信息，微信最终卡片仍需客户端验证。</p></div></details>
 <p class="share-save-state muted small" id="share-save-state">当前版本 ${initial.version}</p><div class="row gap12 wrap"><button class="btn primary" type="submit">保存分享设置</button><button class="btn" type="button" id="share-reset">恢复默认样式</button></div></form>
 <aside class="share-previews"><section class="manage-panel"><h2>横版封面预览</h2><img id="wide-preview" class="wide-preview" src="${imageURL(cover)}" width="1200" height="630" alt="分享横版封面"></section><section class="manage-panel"><h2>微信卡片样式预览</h2><div class="wechat-preview"><div><strong id="share-preview-title">${e(initial.title)}</strong><p id="share-preview-desc">${e(initial.description)}</p></div><img id="square-preview" src="${imageURL(square)}" width="72" height="72" alt="微信分享缩略图"></div><p class="muted tiny mt16">这是本地样式预览，不是微信发送回执。保存后请打开实际分享页验证。</p></section></aside></div>`;
 return {body,after:()=>{
  const form=document.querySelector('#share-config');
  form.querySelectorAll('input,textarea,select,button').forEach(node=>node.setAttribute('data-write',''));
  const setDirty=()=>{dirty=true;document.querySelector('#share-save-state').textContent='有未保存的修改';};
  const update=()=>{setDirty();document.querySelector('#share-preview-title').textContent=form.elements.title.value;document.querySelector('#share-preview-desc').textContent=form.elements.description.value;};
  form.addEventListener('input',update);
  const unguard=registerLeaveGuard(()=>dirty);
  const upload=kind=>async(_,control)=>{
   const file=control.files[0];if(!file)return;
   if(file.size>5*1024*1024)throw new Error('封面不能超过5MB');
   const out=await api('/api/manage/sharing/cover?kind='+kind,{method:'POST',raw:file});
   if(!form.isConnected)return;
   if(kind==='wide'){cover=out.asset;document.querySelector('#wide-preview').src=imageURL(cover);}else{square=out.asset;document.querySelector('#square-preview').src=imageURL(square);}
   setDirty();toast('图片已保存，请继续保存分享设置');
  };
  bind('#share-cover-file','change',upload('wide'));bind('#share-square-file','change',upload('square'));
  bind('#share-config','submit',async(_,f)=>{
   const data=Object.fromEntries(new FormData(f));data.wechat_enabled=f.elements.wechat_enabled.checked;
   saved=await api('/api/manage/sharing',{method:'PUT',data:{...data,version:saved.version,cover,square}});
   dirty=false;document.querySelector('#share-save-state').textContent='已保存 · 版本 '+saved.version;toast('分享设置已更新');
  });
  bind('#share-reset','click',()=>modal('恢复默认分享样式','<p>恢复标题、描述和两张品牌封面；域名及微信配置保持不变。保存后生效。</p>',async()=>{
   form.elements.title.value='机会星图｜找到真正属于你的机会';form.elements.description.value='汇聚官方机会，结合你的关注方向，持续发现、筛选与跟踪值得行动的机会。';
   cover='default-wide.jpg';square='default-square.jpg';document.querySelector('#wide-preview').src=imageURL(cover);document.querySelector('#square-preview').src=imageURL(square);update();
  },'恢复到表单'));
  return ()=>{unguard();form.removeEventListener('input',update);};
 }};
}
