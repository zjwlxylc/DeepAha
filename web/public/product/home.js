import {icon,state} from './core.js';

// Adapted from the supplied v22 OpportunityCarousel; marketing assets are not application data.
export function homeHero(){
 const star=state.user?'/app/star':'/login?next=%2Fapp%2Fstar';
 const slides=[['deepaha-opportunity-map-v2','机会星图',''],['deepaha-official-sources-v2','多源头官方机会汇总','来自官方源头<br>汇聚真实机会'],['deepaha-ai-personalized-v2','个性机会发现','穿过海量机会<br>找到真正属于你的']];
 return `<section class="home-hero" aria-label="机会星图"><div class="home-hero-copy"><span class="marketing-kicker">DEEPAHA · 机会星图</span><h1>让适合你的机会，<br>不再轻易与你擦肩而过。</h1><div class="home-entry-actions"><a class="btn primary" href="${star}" data-nav>我的机会星图 ${icon('arrow','sm')}</a><a class="btn primary" href="/app/overview" data-nav>机会总览</a></div><div class="home-tags"><span>考公</span><span>比赛</span><span>科研</span><span>校招</span></div></div><div class="home-carousel" role="region" aria-roledescription="轮播" aria-label="机会星图海报" tabindex="0">${slides.map(([file,label,copy],i)=>`<div class="home-slide ${i===0?'active':''}" data-slide="${i}" role="group" aria-roledescription="幻灯片" aria-label="${i+1} / 3 · ${label}" ${i?'aria-hidden="true"':''}><picture><source media="(max-width: 767px)" srcset="/product/hero/${file}-768.webp" type="image/webp"><source srcset="/product/hero/${file}-1536.webp" type="image/webp"><img src="/product/hero/${file}-1536.jpg" alt="${label}" width="1536" height="864" ${i?'loading="lazy"':'fetchpriority="high"'} decoding="async"></picture>${copy?`<div class="home-story"><strong>${copy}</strong></div>`:''}</div>`).join('')}<div class="home-carousel-controls"><button type="button" data-carousel="previous" aria-label="上一张海报">${icon('back','sm')}</button><div class="home-dots">${slides.map(([,label],i)=>`<button type="button" data-carousel="${i}" aria-label="显示${label}" aria-pressed="${i===0}"></button>`).join('')}</div><button type="button" data-carousel="next" aria-label="下一张海报">${icon('arrow','sm')}</button><button type="button" data-carousel="pause" aria-label="暂停自动切换">暂停</button></div></div></section>`;
}
export function bindHome(){
 const root=document.querySelector('.home-carousel');if(!root)return ()=>{};
 const media=window.matchMedia('(prefers-reduced-motion: reduce)');
 let current=0,paused=media.matches,hover=false,focus=false,startX=0,startY=0,lastManual=0;
 const pause=root.querySelector('[data-carousel="pause"]');
 function show(n){current=(n+3)%3;root.querySelectorAll('[data-slide]').forEach((el,i)=>{el.classList.toggle('active',i===current);el.setAttribute('aria-hidden',String(i!==current));});root.querySelectorAll('.home-dots button').forEach((el,i)=>el.setAttribute('aria-pressed',String(i===current)));}
 function update(){pause.textContent=paused?'播放':'暂停';pause.setAttribute('aria-label',paused?'开始自动切换':'暂停自动切换');}
 root.addEventListener('click',ev=>{const value=ev.target.closest('[data-carousel]')?.dataset.carousel;if(value===undefined)return;if(value==='pause'){paused=!paused;update();}else {show(value==='next'?current+1:value==='previous'?current-1:Number(value));lastManual=Date.now();}});
 root.addEventListener('keydown',ev=>{if(ev.key==='ArrowRight'||ev.key==='ArrowLeft'){ev.preventDefault();show(current+(ev.key==='ArrowRight'?1:-1));}});
 root.addEventListener('mouseenter',()=>hover=true);root.addEventListener('mouseleave',()=>hover=false);
 root.addEventListener('focusin',()=>focus=true);root.addEventListener('focusout',ev=>{focus=root.contains(ev.relatedTarget);});
 root.addEventListener('touchstart',ev=>{startX=ev.changedTouches[0].clientX;startY=ev.changedTouches[0].clientY;},{passive:true});
 root.addEventListener('touchend',ev=>{const delta=ev.changedTouches[0].clientX-startX;if(Math.abs(delta)>42&&Math.abs(delta)>Math.abs(ev.changedTouches[0].clientY-startY)*1.2){show(current+(delta<0?1:-1));lastManual=Date.now();}},{passive:true});
 const reduced=()=>{if(media.matches){paused=true;update();}};media.addEventListener('change',reduced);
 const timer=setInterval(()=>{if(!paused&&!hover&&!focus&&!document.hidden&&Date.now()-lastManual>5000)show(current+1);},5000);update();
 return ()=>{clearInterval(timer);media.removeEventListener('change',reduced);};
}
