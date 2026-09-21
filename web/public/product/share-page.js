'use strict';
(async()=>{
 const card=document.querySelector('.share-card'),status=document.querySelector('#share-status');
 const link=card.dataset.shareUrl;
 document.querySelector('#copy-share').addEventListener('click',async()=>{
  try{await navigator.clipboard.writeText(link);status.textContent='链接已复制。可粘贴发送，或在微信中打开后从右上角菜单分享。';}
  catch{const field=document.querySelector('#share-link');field.closest('details').open=true;field.focus();field.select();status.textContent='请复制下方已选中的链接。';}
 });
 if(!/MicroMessenger/i.test(navigator.userAgent)||card.dataset.wechat!=='true')return;
 const url=location.href.split('#')[0];
 try{
  const response=await fetch('/api/share/wechat-signature?url='+encodeURIComponent(url),{credentials:'omit',cache:'no-store'});
  if(!response.ok)throw new Error('not ready');
  const data=await response.json();if(!data.enabled){status.textContent='微信专用样式尚未配置，可复制链接访问网站。';return;}
  await new Promise((resolve,reject)=>{
   const s=document.createElement('script');s.src='https://res.wx.qq.com/open/js/jweixin-1.6.0.js';s.onload=resolve;s.onerror=reject;document.head.append(s);
  });
  const wx=window.wx;if(!wx)throw new Error('SDK unavailable');
  const title=document.querySelector('h1').textContent,desc=document.querySelector('#share-description').textContent;
  wx.ready(()=>{
   const value={title,desc,link,imgUrl:card.dataset.shareSquare};
   wx.updateAppMessageShareData({...value,success:()=>{status.textContent='分享样式已准备，可点击微信右上角发送给朋友。';}});
   wx.updateTimelineShareData({title,link,imgUrl:value.imgUrl});
  });
  wx.error(()=>{status.textContent='微信分享样式暂未就绪，可复制链接；请稍后再试。';});
  wx.config({debug:false,appId:data.appId,timestamp:data.timestamp,nonceStr:data.nonceStr,signature:data.signature,jsApiList:data.jsApiList});
 }catch{status.textContent='专用分享样式暂不可用，链接仍可正常打开。';}
})();
