export function birthDateValue(year,month,day,today=new Date()){
 if(!year&&!month&&!day)return {value:'',error:''};
 if(!year||!month||!day)return {value:'',error:'请填写完整的出生日期，或清空后留待填写。'};
 const y=Number(year),m=Number(month),d=Number(day);
 if(!/^\d{4}$/.test(year)||y<1900||y>today.getFullYear())return {value:'',error:'请填写有效的四位出生年份。'};
 const date=new Date(y,m-1,d);
 if(date.getFullYear()!==y||date.getMonth()!==m-1||date.getDate()!==d)return {value:'',error:'该月份没有这一天，请检查日期。'};
 if(date>today)return {value:'',error:'出生日期不能晚于今天。'};
 return {value:`${year}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`,error:''};
}
export function birthDateFields(value=''){
 const valid=/^\d{4}-\d{2}-\d{2}$/.test(value)?value:'';
 const [year='',month='',day='']=valid.split('-');
 const options=(count,selected)=>Array.from({length:count},(_,i)=>`<option value="${i+1}" ${Number(selected)===i+1?'selected':''}>${i+1}</option>`).join('');
 return `<div class="form-field birth-date-field"><div class="between"><span id="birth-date-label">出生日期 <span class="muted tiny">可选</span></span><button class="text-btn" type="button" id="clear-birth-date">清空</button></div><div class="birth-date-inputs" role="group" aria-labelledby="birth-date-label"><label><span class="small muted">年</span><input id="birth-year" aria-label="出生年份" type="text" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" autocomplete="bday-year" placeholder="如 2000" value="${year}"></label><label><span class="small muted">月</span><select id="birth-month" aria-label="出生月份" autocomplete="bday-month"><option value="">月</option>${options(12,month)}</select></label><label><span class="small muted">日</span><select id="birth-day" aria-label="出生日期中的日" autocomplete="bday-day"><option value="">日</option>${options(31,day)}</select></label></div><input type="hidden" id="birth_date" name="birth_date" value="${valid}"></div>`;
}
export function bindBirthDate(form){
 const year=form.querySelector('#birth-year'),month=form.querySelector('#birth-month'),day=form.querySelector('#birth-day'),hidden=form.querySelector('#birth_date');
 const sync=()=>{const result=birthDateValue(year.value,month.value,day.value);hidden.value=result.value;year.setCustomValidity(result.error);};
 for(const control of [year,month,day]){control.addEventListener('input',sync);control.addEventListener('change',sync);}
 form.querySelector('#clear-birth-date').addEventListener('click',()=>{year.value='';month.value='';day.value='';sync();year.dispatchEvent(new Event('input',{bubbles:true}));year.focus();});
 sync();
}
