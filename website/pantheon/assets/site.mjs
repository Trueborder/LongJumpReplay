import {content,site} from './content.mjs';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=v=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0?v:0;
export function eventMarkup(data,t,now=Date.now()/1000){
 if(data?.version!==1||data.fresh!==true||!data.server||!Number.isFinite(data.updated_at)||now-data.updated_at>30||data.updated_at-now>30)return `<div class="event-unavailable"><p>${t.unavailableDetail}</p></div>`;
 const tour=data.tournament,c=data.community;let html='';
 if(tour&&t.phases[tour.state])html+=`<article class="event-card"><p class="event-tag">${t.tournament}</p><h3>${esc(t.phases[tour.state])}</h3><p>${number(tour.players)}/${number(tour.size)} · BO${tour.best_of===3?3:1} · ${esc(tour.policy==='RANDOM'?t.random:tour.policy==='MANUAL'?t.manualModes:tour.mode)}</p><dl><dt>${t.reward}</dt><dd>${esc(tour.summary||t.noRewards)}</dd></dl><a class="text-link" href="${site.account}/economysuite/tournament">${t.registration} ↗</a></article>`;
 else html+=`<p class="empty-event">${t.noTournament}</p>`;
 if(c&&number(c.target)>0&&(number(c.ends_at)===0||c.ends_at>now)&&number(c.progress)<c.target){const pct=Math.min(100,Math.floor(number(c.progress)/c.target*100));html+=`<article class="event-card"><p class="event-tag">${t.community}</p><h3>${esc(c.title)}</h3><progress value="${pct}" max="100" aria-label="${t.progress}"></progress><p>${pct} % · ${number(c.progress).toLocaleString(t.lang)} / ${number(c.target).toLocaleString(t.lang)}</p>${number(c.ends_at)>0?`<p>${t.ends}: ${esc(new Date(c.ends_at*1000).toLocaleString(t.lang,{dateStyle:'medium',timeStyle:'short'}))}</p>`:''}<a class="text-link" href="${site.wiki}/komunitni-cile">${t.communityLink} ↗</a></article>`;}else html+=`<p class="empty-event">${t.noCommunity}</p>`;
 return html;
}
if(typeof document!=='undefined'){
 const t=content[document.documentElement.lang]||content.cs,menu=document.querySelector('#menu-toggle'),nav=document.querySelector('#main-nav'),explore=document.querySelector('.explore');
 const closeMenu=()=>{nav.classList.remove('open');menu.setAttribute('aria-expanded','false');menu.setAttribute('aria-label',t.nav[9]);};
 document.addEventListener('keydown',e=>{document.documentElement.classList.add('keyboard');if(e.key==='Escape'){if(explore.open){explore.open=false;explore.querySelector('summary').focus();}else if(nav.classList.contains('open')){closeMenu();menu.focus();}}});
 document.addEventListener('pointerdown',()=>document.documentElement.classList.remove('keyboard'));
 menu.addEventListener('click',()=>{const open=nav.classList.toggle('open');menu.setAttribute('aria-expanded',String(open));menu.setAttribute('aria-label',open?t.nav[10]:t.nav[9]);});
 nav.addEventListener('click',e=>{if(e.target.closest('a'))closeMenu();});
 document.addEventListener('click',e=>{if(!explore.contains(e.target))explore.open=false;});
 const language=document.querySelector('#language');function languageAnchor(){const url=new URL(language.href);url.hash=location.hash;language.href=url.href;}window.addEventListener('hashchange',languageAnchor);languageAnchor();
 document.querySelector('#copy-address').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(site.address);document.querySelector('#copy-feedback').textContent=t.copied;}catch{const box=document.querySelector('#manual-copy');box.hidden=false;const input=document.querySelector('#server-address');input.focus();input.select();}});
 let fetching=false,lastData=null,signature='';
 function update(data){const fresh=data?.fresh===true&&data.server&&Number.isFinite(data.updated_at)&&Math.abs(Date.now()/1000-data.updated_at)<=30;document.querySelectorAll('[data-server-status]').forEach(el=>{el.dataset.fresh=String(!!fresh);el.textContent=fresh?`${t.online} · ${number(data.server.players)} ${t.players}`:t.unavailable;});
 const stamp=document.querySelector('#updated');stamp.textContent=data?.updated_at?`${t.updated}: ${new Date(data.updated_at*1000).toLocaleTimeString(t.lang,{hour:'2-digit',minute:'2-digit',second:'2-digit'})}`:'';
 const html=eventMarkup(data,t);if(html!==signature){document.querySelector('#event-content').innerHTML=html;signature=html;}document.querySelector('#event-content').setAttribute('aria-busy','false');}
 async function refresh(){if(document.hidden||fetching)return;fetching=true;try{const response=await fetch('/api/status',{credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(7000)});if(!response.ok)throw Error('unavailable');lastData=await response.json();update(lastData);}catch{update({...lastData,fresh:false});}finally{fetching=false;}}
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});setInterval(()=>{if(!document.hidden){if(lastData)update(lastData);refresh();}},15000);refresh();
}
