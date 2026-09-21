/** Pure boundary helpers. No browser storage, identity mocks, or computed qualification. */
export function changedFields(before,after){
 return Object.fromEntries(Object.entries(after).filter(([key,value])=>JSON.stringify(before[key])!==JSON.stringify(value)));
}
export function catalogURL(params,changes={}){
 const q=new URLSearchParams(params);for(const [k,v] of Object.entries(changes)){v===''||v===null?q.delete(k):q.set(k,String(v));}
 return '/app/overview'+(q.size?'?'+q.toString():'');
}
export function returnPath(value){
 if(typeof value!=='string'||value.includes('\\')||/[\r\n]/.test(value))return '/app/overview';
 return /^\/app\/(overview|star|actions|notifications)(\?[^#]*)?$/.test(value)?value:'/app/overview';
}
export function detailURL(id,back='/app/overview'){
 return '/app/opportunity/'+encodeURIComponent(id)+'?return='+encodeURIComponent(returnPath(back));
}
