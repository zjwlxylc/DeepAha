import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
const code=fs.readFileSync('public/product/share-page.js','utf8');
async function probe({agent='MicroMessenger',enabled=true,configured=true,bad=false}={}){
 const calls=[],status={textContent:''};let append=0,signatureURL='',ready;
 const card={dataset:{shareUrl:'https://deepaha.com/share?sv=2',shareSquare:'https://deepaha.com/share-assets/default-square.jpg',wechat:String(enabled)}};
 const items={'.share-card':card,'#share-status':status,'#copy-share':{addEventListener(){}},h1:{textContent:'机会星图'},'#share-description':{textContent:'寻找真正属于你的机会'}};
 const wx={ready(f){ready=f;},error(f){},config(x){calls.push(['config',x]);ready();},updateAppMessageShareData(x){calls.push(['message',x]);x.success();},updateTimelineShareData(x){calls.push(['timeline',x]);}};
 const context={navigator:{userAgent:agent,clipboard:{}},document:{querySelector:s=>items[s],head:{append(s){append++;s.onload();}},createElement(){return {};}},window:{wx},location:{href:'https://deepaha.com/share?sv=2#fragment'},encodeURIComponent,fetch:async url=>{signatureURL=url;return {ok:!bad,json:async()=>({enabled:configured,appId:'wxexample',timestamp:123,nonceStr:'n',signature:'s',jsApiList:['updateAppMessageShareData','updateTimelineShareData']})};}};
 await vm.runInNewContext(code,context);
 return {calls,status,append,signatureURL};
}
let r=await probe();assert.equal(r.calls.length,3);assert.equal(r.append,1);assert.ok(!decodeURIComponent(r.signatureURL).includes('#fragment'));assert.equal(r.calls[0][1].debug,false);assert.equal(r.calls[1][1].imgUrl,'https://deepaha.com/share-assets/default-square.jpg');assert.ok(r.status.textContent.includes('已准备'));assert.ok(!r.status.textContent.includes('分享成功'));
r=await probe({agent:'Chrome'});assert.equal(r.append,0);assert.equal(r.signatureURL,'');
r=await probe({enabled:false});assert.equal(r.signatureURL,'');
r=await probe({configured:false});assert.equal(r.append,0);assert.ok(r.status.textContent.includes('尚未配置'));
r=await probe({bad:true});assert.equal(r.append,0);assert.ok(r.status.textContent.includes('链接仍可正常打开'));
console.log('SHARE_R3_JS=PASS: 15 assertions; simulated SDK only, not WeChat client evidence');
