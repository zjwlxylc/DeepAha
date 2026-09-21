/** Presentation helpers only. Eligibility, ranking and time authority stay on the server. */
export function internalPath(value){
 return typeof value==='string'&&value.startsWith('/')&&!value.startsWith('//')&&!/[\\\u0000-\u001f\u007f]/.test(value)?value:'/';
}
export function defaultActionView(requested,width){return requested==='board'||requested==='list'?requested:width<=620?'list':'board';}
export function readableAction(action){return action?.saved?({SAVED:'已收藏',PREPARING:'准备中',APPLIED:'已申请',WAITING:'等待结果',COMPLETED:'已完成',DISMISSED:'暂不考虑'}[action.status]||'已在行动中'):'收藏机会';}
export function filterCount(params){return ['q','kind','region'].filter(k=>Boolean(params.get(k)?.trim())).length;}
export function compactCount(value){return value>99?'99+':value>0?String(value):'';}
export function workspaceReturn(value,fallback){
 return typeof value==='string'&&internalPath(value)===value&&(value===fallback||value.startsWith(fallback+'?'))?value:fallback;
}
export function publicNote(value){
 return String(value??'').replace(/^本份返回有(\d+)项共同内容尚未定位引用，原文与对应备注已保留。$/,'有 $1 项公告内容的引用位置待核对，详情中保留原文。');
}
export function withQuery(path,params,changes={}){
 const query=new URLSearchParams(params);
 for(const [key,value] of Object.entries(changes))value===''||value===null?query.delete(key):query.set(key,String(value));
 return internalPath(path)+(query.size?'?'+query:'');
}
