/** Re-group existing controls without cloning, dropping values or changing field contracts. */
export function arrangeProfile(form){
 const field=name=>{const control=form.elements.namedItem(name);return (control?.nodeType?control:control?.[0])?.closest('.form-field,.checkbox-field');};
 function group(title,names,open=false){
  const details=document.createElement('details');details.className='profile-group span2';details.open=open;
  const summary=document.createElement('summary');summary.textContent=title;details.append(summary);
  const body=document.createElement('div');body.className='profile-group-body';details.append(body);
  for(const name of names){const node=field(name);if(node)body.append(node);}
  return details;
 }
 const direction=group('关注方向',['opportunity_types','cities','region_preference_mode','career_directions','interests','goals','skills','constraints','personalization_enabled'],true);
 const basic=group('基本资料',['display_name','education','major','graduation_year'],!form.elements.major?.value);
 const advanced=form.querySelector('.profile-advanced');advanced.classList.add('profile-group');
 const advancedBody=advanced.querySelector('.profile-form');for(const name of ['major_code','birth_date','hukou_region']){const node=field(name);if(node)advancedBody.append(node);}
 const notifications=document.createElement('details');notifications.className='profile-group span2';notifications.innerHTML='<summary>消息与提醒</summary>';
 notifications.append(form.querySelector('.notification-settings'));
 const save=form.querySelector('button[type=submit]').parentElement;save.className='profile-save-bar span2';
 form.prepend(direction,basic,advanced,notifications);form.append(save);
 return save;
}
