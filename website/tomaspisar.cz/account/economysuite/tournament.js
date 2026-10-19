(function (root) {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const plain = value => String(value || '').replace(/[&§][0-9a-fk-or]/gi,'');
  const skin = value => /^https:\/\/textures\.minecraft\.net\/texture\/[a-f0-9]{32,64}$/.test(value||'') ? value : '';
  const phases = {DRAFT:['Příprava','Draft'],REGISTRATION:['Registrace otevřena','Registration open'],LOCKED:['Přesun do lobby','Lobby transfer'],ROUND_READY:['Kolo připraveno','Round ready'],ROUND_ACTIVE:['Hraje se','Playing'],INTERMISSION:['Pauza mezi koly','Intermission'],PAUSED:['Pozastaveno','Paused'],COMPLETED:['Dokončeno','Completed'],CANCELLED:['Zrušeno','Cancelled']};
  const stages = {Quarterfinal:['Čtvrtfinále','Quarterfinal'],Semifinal:['Semifinále','Semifinal'],Final:['Finále','Final'],Bronze:['O třetí místo','Third place']};
  const destructive = new Set(['cancel','forcewin','rematch','disqualify','remove','substitute','remove_prize','clear_prizes','preset','announce']);
  let state=null,ctx=null,pollTimer=null,clockTimer=null,busy=false,loading=false,reauth='',selectedHistory='',lastOperations='',serverOffset=0,resizeBound=false;
  const head = p => `<span class="tw-head" data-skin="${esc(skin(p?.skin))}" aria-hidden="true"><span>${esc(p?.name?.slice(0,2)||'?')}</span><canvas width="32" height="32" hidden></canvas></span>`;
  function playerLine(id,s,score,winner,own) {
    const p=[...(s.players||[]),...(s.waitlist||[])].find(p=>p.uuid===id);
    return `<div class="tw-player ${winner===id?'is-winner':''} ${own===id?'is-you':''}">${head(p)}<span>${esc(p?.name||'TBD')}</span><strong>${Number(score)||0}</strong>${winner===id?'<span class="tw-crown" aria-label="Winner">♛</span>':''}</div>`;
  }
  function bracket(s,t,own) {
    const matches=[...(s.matches||[])];
    if(matches.length&&[2,4,8].includes(s.size)){
      const total=Math.log2(s.size);
      for(let round=2;round<=total;round++)if(!matches.some(m=>m.round===round&&m.label!=='Bronze')){
        const previous=matches.filter(m=>m.round===round-1&&m.label!=='Bronze');
        for(let i=0;i<s.size/2**round;i++)matches.push({id:`pending-${round}-${i}`,round,label:round===total?'Final':'Semifinal',first:previous[i*2]?.winner||'',second:previous[i*2+1]?.winner||'',state:'PENDING',placeholder:true});
      }
      if(s.size>2&&!matches.some(m=>m.label==='Bronze'))matches.push({id:'pending-bronze',round:total,label:'Bronze',first:'',second:'',state:'PENDING',placeholder:true});
    }
    const rounds=[...new Set(matches.filter(m=>m.label!=='Bronze').map(m=>m.round))].sort((a,b)=>a-b);
    if(!matches.length)return `<div class="tw-empty"><span aria-hidden="true">⚔</span><h3>${esc(t('Pavouk čeká na hráče','The bracket awaits its players'))}</h3><p>${esc(t('Dvojice se sestaví po uzamčení registrace.','Pairings appear when registration is locked.'))}</p></div>`;
    const card=m=>`<button type="button" class="tw-match ${m.state==='RUNNING'?'is-live':''} ${m.first===own||m.second===own?'is-own':''} ${m.winner?'has-winner':''}" ${m.placeholder?'disabled':`data-match="${esc(m.id)}"`}><span class="tw-match-meta"><span>${esc(m.mode||t('Mód vybere admin','Mode pending'))}</span><span>${m.state==='RUNNING'?esc(t('● ŽIVĚ','● LIVE')):m.state==='COMPLETE'?esc(t('Dohráno','Finished')):m.state==='ADMIN_DECISION'?esc(t('Rozhodnutí admina','Admin decision')):esc(t('Čeká','Waiting'))}</span></span>${playerLine(m.first,s,m.first_score,m.winner,own)}${playerLine(m.second,s,m.second_score,m.winner,own)}<span class="tw-match-arena">${esc(m.arena||t('Automatická aréna','Automatic arena'))} · BO${s.best_of}</span></button>`;
    return `<div class="tw-bracket" style="--rounds:${rounds.length}">${rounds.map(r=>`<section class="tw-round"><h3>${esc(t(...(stages[matches.find(m=>m.round===r&&m.label!=='Bronze')?.label]||['Kolo '+r,'Round '+r])))}</h3><div class="tw-round-matches">${matches.filter(m=>m.round===r&&m.label!=='Bronze').map(card).join('')}</div></section>`).join('')}</div>${matches.some(m=>m.label==='Bronze')?`<section class="tw-bronze"><h3>${esc(t('Zápas o třetí místo','Third-place match'))}</h3>${matches.filter(m=>m.label==='Bronze').map(card).join('')}</section>`:''}`;
  }
  const stamp = s => ({tournament_id:s.id,revision:s.revision,instance:s.instance});
  function standings(s) {
    if(s?.state!=='COMPLETED')return [];
    const ranks=new Map();for(const m of s.matches||[]){if(m.label==='Final'){if(m.winner)ranks.set(m.winner,1);if(m.loser)ranks.set(m.loser,2);}else if(m.label==='Bronze'){if(m.winner)ranks.set(m.winner,3);if(m.loser)ranks.set(m.loser,4);}else if(m.label==='Quarterfinal'&&m.loser)ranks.set(m.loser,5);}
    return (s.players||[]).filter(p=>ranks.has(p.uuid)).map(p=>({...p,place:ranks.get(p.uuid)})).sort((a,b)=>a.place-b.place);
  }
  function nextAction(s,t) {
    if(!s.id)return {label:t('Vytvoř turnaj v nastavení níže','Create a tournament below'),disabled:true};
    if(s.celebrating)return {label:t('Probíhá vyhlášení','Award ceremony in progress'),disabled:true};
    if(s.state==='LOCKED')return {label:t('Probíhá přesun do lobby','Players are moving to the lobby'),disabled:true};
    if(s.state==='ROUND_ACTIVE')return {label:t('Zbývající zápasy: ','Remaining matches: ')+s.matches.filter(m=>m.round===s.round&&m.state!=='COMPLETE').length,disabled:true};
    if(s.state==='INTERMISSION')return {label:t('Probíhá povinná pauza','Mandatory intermission'),disabled:true};
    if(['COMPLETED','CANCELLED'].includes(s.state))return {label:t('Nový turnaj vytvoříš níže','Create the next tournament below'),disabled:true};
    const labels={DRAFT:['Otevřít registraci','Open registration'],REGISTRATION:['Uzamknout registraci','Lock registration'],ROUND_READY:['Spustit další kolo','Start next round'],PAUSED:['Obnovit turnaj','Resume tournament']};
    return {label:t(...(labels[s.state]||['Čeká se','Waiting'])),disabled:!labels[s.state]||(['REGISTRATION','ROUND_READY'].includes(s.state)&&(s.problems||[]).length>0)};
  }
  function renderLive() {
    const {t,admin}=ctx,s=state?.snapshot;
    if(!s)return `<section class="es-panel tw-empty"><h2>${esc(t('Čekáme na turnajový server','Waiting for the tournament server'))}</h2><p>${esc(t('Turnaje budou dostupné po aktualizaci pluginu a prvním propojení.','Tournaments appear after the plugin update and first synchronization.'))}</p></section>`;
    const historical=selectedHistory?(state.history||[]).find(h=>h.id===selectedHistory):null,view=historical||s;
    const own=state.uuid,p=[...(view.players||[]),...(view.waitlist||[])].find(p=>p.uuid===own),joined=!!p;
    const eligible=(s.online||[]).find(p=>p.uuid===own)?.eligible; // Server also validates every request.
    const online=state.player_online===true||eligible;
    const ownMatch=(view.matches||[]).find(m=>m.round===view.round&&(m.first===own||m.second===own));
    const others=[...(view.players||[]),...(view.waitlist||[])];
    const opponent=ownMatch?others.find(p=>p.uuid===(ownMatch.first===own?ownMatch.second:ownMatch.first)):null;
    return `<section class="tw-hero"><div><p class="es-eyebrow">PANTHEON / PvP</p><h2>${esc(t(...(phases[view.state]||['Aréna čeká','The arena awaits'])))}</h2><p>${view.size} ${esc(t('hráčů','players'))} · BO${view.best_of} · ${esc(view.policy==='SAME'?view.mode:t('Více módů','Multiple modes'))}</p></div><div class="tw-live ${state.fresh?'':'is-stale'}"><span>${esc(state.fresh?t('● Živě','● Live'):t('○ Server neodpovídá — pouze náhled','○ Server offline — read only'))}</span><small>${esc(t('Aktualizováno','Updated'))}: ${state.synced_at?new Date(state.synced_at*1000).toLocaleTimeString():'—'}</small><strong data-tw-countdown></strong></div></section>
      ${!historical?`<section class="es-panel tw-own"><div><small>${esc(t('TVŮJ TURNAJ','YOUR TOURNAMENT'))}</small><h3>${esc(joined?p.name:t('Ještě nejsi přihlášen/a','You have not joined'))}</h3><p>${esc(opponent?t('Soupeř: ','Opponent: ')+opponent.name:joined?(view.waitlist||[]).some(p=>p.uuid===own)?t('Jsi na čekací listině.','You are on the waiting list.'):t('Sleduj přípravu svého dalšího zápasu.','Watch for your next match.'):t('Pro přihlášení propoj účet a přihlas se v Minecraftu.','Pair your account and sign in to Minecraft to join.'))}</p></div>${s.state==='REGISTRATION'?`<button class="es-primary" data-tw-action="${joined?'leave':'join'}" ${!state.fresh||!own||!online?'disabled':''}>${esc(joined?t('Odhlásit se','Leave'):t('Přihlásit se','Join'))}</button>`:''}</section>`:''}
      <section class="es-panel tw-arena"><div class="tw-section-heading"><h2>${esc(t('Turnajový pavouk','Tournament bracket'))}</h2><span>${view.players.length}/${view.size} · ${esc(t('Kolo','Round'))} ${view.round||'—'}</span></div>${bracket(view,t,own)}</section>
      <div class="tw-detail-grid"><section class="es-panel"><h2>${esc(t('Odměny','Rewards'))}</h2><p class="tw-prize-total">${esc(plain(view.summary)||t('Odměny zatím nejsou nastavené','Rewards not set yet'))}</p>${[...new Set((view.prizes||[]).map(p=>p.place))].map(place=>`<div class="tw-prize-row"><strong>${place===5?'5.–8.':place+'.'} ${esc(t('místo','place'))}</strong><span>${view.prizes.filter(p=>p.place===place).map(p=>esc(plain(p.description))).join(' · ')}</span></div>`).join('')}<p class="es-muted">${esc(t('Výhry najdeš po turnaji v /mailbox.','Your prizes arrive in /mailbox after the tournament.'))}</p></section><section class="es-panel"><h2>${esc(t('Účastníci a čekatelé','Players and waiting list'))}</h2>${[...view.players,...view.waitlist].map(p=>`<div class="tw-roster">${head(p)}<strong>${esc(p.name)}</strong><span>${esc(view.waitlist.some(w=>w.uuid===p.uuid)?t('Čekatel','Waiting list'):p.online?t('Online','Online'):t('Offline','Offline'))}</span></div>`).join('')||`<p>${esc(t('Zatím nikdo.','No players yet.'))}</p>`}</section></div>
      ${admin&&state.admin&&!historical?`<section class="tw-next"><div><small>${esc(t('DALŠÍ FÁZE','NEXT PHASE'))}</small><strong>${esc(nextAction(s,t).label)}</strong><p>${esc(s.problems?.join(' · ')||t('Každý zásah znovu ověří herní server.','Every change is validated by the game server.'))}</p></div><button class="es-primary" data-tw-action="advance" ${!state.fresh||nextAction(s,t).disabled?'disabled':''}>${esc(t('Pokračovat','Continue'))} →</button></section>`:''}
      <section class="es-panel"><h2>${esc(t('Historie turnajů','Tournament history'))}</h2><select id="tw-history" aria-label="${esc(t('Turnaj','Tournament'))}"><option value="">${esc(t('Aktuální turnaj','Current tournament'))}</option>${(state.history||[]).map(h=>`<option value="${esc(h.id)}" ${selectedHistory===h.id?'selected':''}>${esc(h.id.slice(0,8))} · ${h.size} · ${esc(t(...(phases[h.state]||['Turnaj','Tournament'])))}</option>`).join('')}</select></section>
      <section class="es-panel tw-operation-log" aria-live="polite"><h2>${esc(t('Poslední požadavky','Recent requests'))}</h2>${(state.operations||[]).slice(0,5).map(o=>`<p data-operation="${esc(o.id)}"><strong>${esc(o.action)}</strong> · ${esc(o.state)} — ${esc(plain(o.result||t('Čeká na potvrzení serveru','Waiting for server confirmation')))}</p>`).join('')}</section>`;
  }
  function adminPanel() {
    const {t}=ctx,s=state?.snapshot;if(!state?.admin)return `<section class="es-panel"><h2>${esc(t('Nemáš přístup do administrace','Administration access denied'))}</h2></section>`;
    if(!s)return '';
    const choiceLabel=v=>({SAME:t('Společný mód','Shared mode'),RANDOM:t('Náhodné módy','Random modes'),MANUAL:t('Ruční výběr','Manual selection'),true:t('Ano','Yes'),false:t('Ne','No'),coins:t('Coiny','Coins'),items:t('Předměty','Items'),keys:t('Klíče','Keys'),cosmetics:t('Kosmetika','Cosmetics'),mod:t('MOD předměty','MOD items')}[v]||v);
    const timeLabel=key=>({'inter-match-delay-seconds':t('Pauza mezi zápasy','Inter-match delay'),'reconnect-grace-seconds':t('Lhůta na opětovné připojení','Reconnect grace'),'sudden-death-seconds':t('Náhlá smrt','Sudden death'),'waiting-reminder-seconds':t('Připomenutí čekajícím','Waiting reminder')}[key]||key);
    const opt=(list,value)=>list.map(v=>`<option value="${esc(v)}" ${v===value?'selected':''}>${esc(choiceLabel(v))}</option>`).join('');
    const field=(key,label,value='',type='text')=>`<label>${esc(label)}<input name="${esc(key)}" type="${type}" value="${esc(value)}" required></label>`;
    const select=(key,label,list,value)=>`<label>${esc(label)}<select name="${key}">${opt(list,value)}</select></label>`;
    const form=(action,label,fields,disabled=false)=>`<form class="tw-form" data-tw-form="${action}" data-stamp="${esc(JSON.stringify(stamp(s)))}">${fields}<button type="submit" ${disabled?'disabled':''}>${esc(label)}</button></form>`;
    const live=s.id&&!['COMPLETED','CANCELLED'].includes(s.state),editable=!s.id||['DRAFT','REGISTRATION','COMPLETED','CANCELLED'].includes(s.state),names=s.players.map(p=>p.name),online=s.online.map(p=>p.name),matchIds=s.matches.map(m=>m.id),placeOptions=s.size===8?['1','2','3','4','5']:Array.from({length:s.size},(_,i)=>String(i+1));
    const rules=select('size',t('Počet hráčů','Players'),['2','4','8'],String(s.size))+select('best_of','BO',['1','3'],String(s.best_of))+select('policy',t('Výběr módů','Mode policy'),['SAME','RANDOM','MANUAL'],s.policy)+select('mode',t('Společný mód','Shared mode'),s.modes,s.mode);
    const section=(name,content)=>`<details class="es-panel tw-admin-section"><summary>${esc(name)}</summary>${content}</details>`;
    return `<section class="es-panel tw-admin-intro"><h2>${esc(t('Řídicí místnost','Control room'))}</h2><p>${esc(t('Změny platí až po potvrzení herním serverem. Při souběžné změně obnov formuláře.','Changes apply only after server confirmation. Refresh forms after concurrent changes.'))}</p><button type="button" data-refresh-admin>${esc(t('Obnovit formuláře podle aktuálního stavu','Refresh forms from current state'))}</button><span id="tw-form-stale" aria-live="polite"></span></section>
      ${section(t('Nastavení turnaje','Tournament settings'),form(live?'rules':'create',live?t('Uložit pravidla','Save rules'):t('Vytvořit turnaj','Create tournament'),rules,!editable)+form('pool',t('Uložit pool','Save pool'),field('modes',t('Módy oddělené čárkou','Comma-separated modes'),s.pool.join(',')),!editable)+form('seeding',t('Uložit nasazení','Save seeding'),select('random',t('Náhodné nasazení','Random seeding'),['true','false'],String(s.random_seeding)),!editable))}
      ${section(t('Hráči a nasazení','Players and seeding'),!live?`<p>${esc(t('Nejprve vytvoř turnaj.','Create a tournament first.'))}</p>`:form('add',t('Přidat hráče','Add player'),select('player',t('Online hráč','Online player'),online))+form('remove',t('Odebrat hráče','Remove player'),select('player',t('Účastník','Participant'),[...names,...s.waitlist.map(p=>p.name)]))+form('substitute',t('Nahradit hráče','Replace player'),select('player',t('Účastník','Participant'),names)+select('replacement',t('Náhradník','Replacement'),online))+form('seed',t('Změnit pořadí','Move seed'),select('player',t('Hráč','Player'),s.players.map(p=>p.uuid))+select('direction',t('Posun','Direction'),['-1','1'])))}
      ${section(t('Zápasy a arény','Matches and arenas'),!s.matches.length?`<p>${esc(t('Zápasy vzniknou po uzamčení registrace.','Matches are created when registration is locked.'))}</p>`:form('mode',t('Změnit mód','Change mode'),select('match',t('Zápas','Match'),matchIds)+select('mode',t('Mód','Mode'),s.modes))+form('arena',t('Přiřadit arénu','Assign arena'),select('match',t('Zápas','Match'),matchIds)+select('arena',t('Aréna — prázdná znamená automaticky','Arena — empty means automatic'),['',...s.arenas]))+form('rematch',t('Potvrdit odvetu','Confirm rematch'),select('match',t('Zápas','Match'),matchIds))+form('forcewin',t('Rozhodnout vítěze','Force winner'),select('match',t('Zápas','Match'),matchIds)+select('player',t('Vítěz','Winner'),names))+form('disqualify',t('Diskvalifikovat','Disqualify'),select('player',t('Hráč','Player'),names)))}
      ${section(t('Odměny a presety','Rewards and presets'),!live?`<p>${esc(t('Nejprve vytvoř turnaj.','Create a tournament first.'))}</p>`:form('prize',t('Přidat měnu','Add currency'),select('place',t('Umístění','Place'),placeOptions)+select('type',t('Měna','Currency'),['coins','tokens'])+field('amount',t('Částka','Amount'),100,'number'))+`<label>${esc(t('Hledat v katalogu giveaway','Search giveaway catalogue'))}<input id="tw-search" type="search"></label><label>${esc(t('Kategorie','Category'))}<select id="tw-category"><option value="">${esc(t('Všechny','All'))}</option>${opt([...new Set(s.catalog.map(p=>p.category))])}</select></label>`+form('catalog_prize',t('Přidat vybranou odměnu','Add selected reward'),select('place',t('Umístění','Place'),placeOptions)+`<label>${esc(t('Katalog /giveaway','/giveaway catalogue'))}<select id="tw-catalog" name="id">${s.catalog.map(p=>`<option value="${esc(p.id)}" data-category="${esc(p.category)}">${esc(plain(p.name))} · ${p.amount} · ${esc(p.category)}</option>`).join('')}</select></label>`+field('count',t('Počet kopií','Copies'),1,'number')+`<input type="hidden" name="catalog_revision" value="${esc(s.catalog_revision)}">`)+form('preset',t('Použít preset — nahradí odměny','Apply preset — replaces rewards'),select('preset',t('Preset','Preset'),s.presets.map(p=>p.id)))+s.presets.map(p=>`<p><strong>${esc(plain(p.name))}</strong>: ${esc(plain(p.summary))}</p>`).join('')+form('remove_prize',t('Vymazat odměny umístění','Clear selected place'),select('place',t('Umístění','Place'),placeOptions)+`<input type="hidden" name="index" value="-1">`)+form('clear_prizes',t('Vymazat všechny odměny','Clear all rewards'),''))}
      ${live?section(t('Jednotlivé odměny','Individual prizes'),s.prizes.map(p=>form('remove_prize',t('Odebrat: ','Remove: ')+plain(p.description),`<strong>${p.place===5?'5.–8.':p.place+'.'} ${esc(t('místo','place'))}</strong><input type="hidden" name="place" value="${p.place}"><input type="hidden" name="index" value="${p.index}">`)).join('')||esc(t('Zatím žádné odměny.','No prizes yet.'))):''}
      ${section(t('Časy a automatika','Timing and automation'),Object.entries(s.times).map(([key,value])=>form('time',t('Uložit čas','Save time'),`<input type="hidden" name="key" value="${esc(key)}">`+field('seconds',timeLabel(key)+' (s)',value,'number'))).join('')+form('automatic',t('Uložit pokračování','Save progression'),select('enabled',t('Automaticky pokračovat','Advance automatically'),['true','false'],String(s.automatic))))}
      ${section(t('Oznámení, zásahy a diagnostika','Announcements, controls and diagnostics'),form('announce',t('Náhled oznámení','Preview announcement'),`<input type="hidden" name="preview" value="true">`,s.state!=='REGISTRATION')+form('announce',t('Publikovat oznámení ve hře','Publish announcement in game'),`<input type="hidden" name="preview" value="false">`,s.state!=='REGISTRATION')+['pause','recover','cleanup','cancel'].map((a,i)=>form(a,t(...[['Pozastavit','Pause'],['Obnovit','Resume'],['Uklidit arény','Clean arenas'],['Zrušit turnaj','Cancel tournament']][i]),'',!live&&a!=='cleanup')).join('')+`<ul>${s.problems.map(p=>`<li>${esc(plain(p))}</li>`).join('')||`<li>${esc(t('Žádné zjištěné problémy. Živý test může odhalit omezení dalších pluginů.','No detected problems. A live test may reveal restrictions from other plugins.'))}</li>`}</ul>`)}
      <dialog id="tw-reauth" class="tw-dialog"><form id="tw-reauth-form"><h2>${esc(t('Ověření administrátora','Administrator verification'))}</h2><p>${esc(t('Heslo se neukládá do prohlížeče. Ověření platí deset minut.','Your password is not stored in the browser. Verification lasts ten minutes.'))}</p><label>${esc(t('Heslo','Password'))}<input name="password" type="password" autocomplete="current-password" required></label><button type="submit">${esc(t('Ověřit','Verify'))}</button><button type="button" data-close-reauth>${esc(t('Zrušit','Cancel'))}</button></form></dialog>`;
  }
  function render(context) {ctx={...ctx,...context};return `<div id="tw-live">${renderLive()}</div>${context.admin?`<div id="tw-admin">${adminPanel()}</div>`:''}<dialog id="tw-match-detail" class="tw-dialog"><div id="tw-match-content"></div><form method="dialog"><button>${esc(context.t('Zavřít','Close'))}</button></form></dialog>`;}
  async function load(api){state=await api('/api/economysuite/tournament');serverOffset=Date.now()-state.server_time*1000;}
  function drawHeads() {
    document.querySelectorAll('.tw-head[data-skin]').forEach(el=>{
      const url=skin(el.dataset.skin);if(!url||el.dataset.loaded)return;el.dataset.loaded='true';const img=new Image();
      img.onload=()=>{const canvas=el.querySelector('canvas'),c=canvas?.getContext('2d');if(!c||!el.isConnected)return;c.imageSmoothingEnabled=false;const unit=img.width/64;c.drawImage(img,8*unit,8*unit,8*unit,8*unit,0,0,32,32);if(img.height>=16*unit)c.drawImage(img,40*unit,8*unit,8*unit,8*unit,0,0,32,32);canvas.hidden=false;el.querySelector('span').hidden=true;};
      img.onerror=()=>{el.dataset.loaded='failed';};img.src=url;
    });
  }
  function drawConnections() {
    document.querySelectorAll('.tw-bracket').forEach(board=>{
      board.querySelector('svg.tw-connectors')?.remove();const columns=[...board.querySelectorAll('.tw-round')];if(columns.length<2)return;
      const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),bounds=board.getBoundingClientRect();svg.setAttribute('class','tw-connectors');svg.setAttribute('aria-hidden','true');svg.setAttribute('width',board.scrollWidth);svg.setAttribute('height',board.scrollHeight);
      for(let round=0;round<columns.length-1;round++){
        const from=[...columns[round].querySelectorAll('.tw-match')],to=[...columns[round+1].querySelectorAll('.tw-match')];
        from.forEach((card,i)=>{const target=to[Math.floor(i/2)];if(!target)return;const a=card.getBoundingClientRect(),b=target.getBoundingClientRect(),x1=a.right-bounds.left+board.scrollLeft,x2=b.left-bounds.left+board.scrollLeft,y1=a.top+a.height/2-bounds.top,y2=b.top+b.height/2-bounds.top;
          const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',`M${x1},${y1} H${(x1+x2)/2} V${y2} H${x2}`);path.setAttribute('fill','none');path.setAttribute('stroke',card.classList.contains('has-winner')?'#59a683':card.classList.contains('is-live')?'#9a75c8':'#c8bedb');path.setAttribute('stroke-width','2');svg.append(path);
        });
      }board.prepend(svg);
    });
  }
  function updateClock(){const el=document.querySelector('[data-tw-countdown]');if(!el)return;const s=state?.snapshot,left=state?.fresh&&s?.deadline?Math.max(0,s.deadline-Math.floor((Date.now()-serverOffset)/1000)):null;el.textContent=left===null?'':`${Math.floor(left/60)}:${String(left%60).padStart(2,'0')}`;}
  function confirmChange(description,destructiveAction) {
    if(root.LJR_FEEDBACK?.['confirm'])return root.LJR_FEEDBACK['confirm']({title:ctx.t('Potvrdit zásah','Confirm change'),description,confirmLabel:ctx.t('Potvrdit','Confirm'),cancelLabel:ctx.t('Zrušit','Cancel'),destructive:destructiveAction});
    return new Promise(resolve=>{const focus=document.activeElement,dialog=document.createElement('dialog');dialog.className='tw-dialog';dialog.innerHTML=`<form method="dialog"><h2>${esc(ctx.t('Potvrdit zásah','Confirm change'))}</h2><p>${esc(description)}</p><button value="cancel">${esc(ctx.t('Zrušit','Cancel'))}</button><button value="accept">${esc(ctx.t('Potvrdit','Confirm'))}</button></form>`;document.body.append(dialog);dialog.addEventListener('close',()=>{const accepted=dialog.returnValue==='accept';dialog.remove();focus?.focus();resolve(accepted);},{once:true});dialog.showModal();});
  }
  async function send(action,payload={},expected=stamp(state.snapshot)) {
    if(busy)return;busy=true;
    try {
      if(!state.fresh)throw new Error(ctx.t('Server neodpovídá. Obnov stránku.','Server is unavailable. Refresh the page.'));
      if(destructive.has(action)){
        const description=`${action} · ${Object.values(payload).join(' · ')}`;
        const approved=await confirmChange(description,action!=='announce');
        if(!approved)return;
      }
      const body={...expected,action,payload,idempotency_key:crypto.randomUUID(),confirm:true,reauth_token:reauth};
      try{await ctx.api('/api/economysuite/tournament/action',body);}
      catch(e){if(e.status===403&&state.admin){document.querySelector('#tw-reauth').showModal();document.querySelector('#tw-reauth input').focus();ctx.status(ctx.t('Ověř heslo a akci potom zvol znovu.','Verify your password, then select the action again.'),false);return;}throw e;}
      ctx.status(ctx.t('Požadavek čeká na potvrzení serverem.','Request is waiting for server confirmation.'),false);await poll();
    }catch(e){ctx.status(e.message,true);}finally{busy=false;}
  }
  function bindLive() {
    const shown=selectedHistory?state.history.find(h=>h.id===selectedHistory):state?.snapshot;
    const results=standings(shown);if(results.length){const panel=document.createElement('section');panel.className='es-panel tw-standings';panel.innerHTML=`<h2>${esc(ctx.t('Konečné pořadí','Final standings'))}</h2>${results.map(p=>`<div class="tw-roster"><strong>${p.place===5?'5.–8.':p.place+'.'}</strong>${head(p)}<span>${esc(p.name)}</span></div>`).join('')}`;document.querySelector('.tw-arena')?.before(panel);}
    document.querySelectorAll('[data-match]').forEach(card=>{const m=shown?.matches.find(m=>m.id===card.dataset.match);if(m?.time){const time=document.createElement('small');time.className='tw-running-time';time.textContent=plain(m.phase)+' · '+m.time;card.append(time);}});
    const own=shown?.players.find(p=>p.uuid===state.uuid),ownHost=document.querySelector('.tw-own>div');
    if(own?.status&&ownHost){const status=document.createElement('p');status.textContent=plain(own.status)+' · '+plain(own.detail);ownHost.append(status);}
    document.querySelectorAll('[data-tw-action]').forEach(b=>b.onclick=()=>send(b.dataset.twAction));
    document.querySelector('#tw-history')?.addEventListener('change',e=>{selectedHistory=e.target.value;refreshLive();});
    document.querySelectorAll('[data-match]').forEach(b=>b.onclick=()=>{
      const s=selectedHistory?state.history.find(h=>h.id===selectedHistory):state.snapshot,m=s?.matches.find(m=>m.id===b.dataset.match);if(!m)return;
      document.querySelector('#tw-match-content').innerHTML=`<h2>${esc(ctx.t(...(stages[m.label]||['Zápas','Match'])))}</h2>${playerLine(m.first,s,m.first_score,m.winner,state.uuid)}${playerLine(m.second,s,m.second_score,m.winner,state.uuid)}<p>${esc(m.mode)} · ${esc(m.arena)} · ${esc(m.state)}</p><p>${esc(ctx.t('Sledování ve hře: /tournament spectate','Watch in Minecraft: /tournament spectate'))}</p>`;
      document.querySelector('#tw-match-detail').showModal();drawHeads();
    });drawHeads();drawConnections();updateClock();
  }
  function bindAdmin() {
    document.querySelector('[data-refresh-admin]')?.addEventListener('click',()=>{document.querySelector('#tw-admin').innerHTML=adminPanel();bindAdmin();});
    document.querySelectorAll('[data-tw-form]').forEach(form=>{const button=form.querySelector('button');button.dataset.phaseDisabled=String(button.disabled);form.addEventListener('submit',e=>{
      e.preventDefault();const payload=Object.fromEntries(new FormData(form));for(const k of ['preview','enabled','random'])if(k in payload)payload[k]=payload[k]==='true';send(form.dataset.twForm,payload,JSON.parse(form.dataset.stamp));
    });});
    const filter=()=>{const search=(document.querySelector('#tw-search')?.value||'').toLocaleLowerCase(),category=document.querySelector('#tw-category')?.value;document.querySelectorAll('#tw-catalog option').forEach(o=>{o.hidden=!!((category&&o.dataset.category!==category)||!o.textContent.toLocaleLowerCase().includes(search));o.disabled=o.hidden;});const select=document.querySelector('#tw-catalog');if(select&&select.selectedOptions[0]?.disabled)select.value=[...select.options].find(o=>!o.disabled)?.value||'';};
    document.querySelector('#tw-search')?.addEventListener('input',filter);document.querySelector('#tw-category')?.addEventListener('change',filter);
    document.querySelector('[data-close-reauth]')?.addEventListener('click',()=>document.querySelector('#tw-reauth').close());
    document.querySelector('#tw-reauth-form')?.addEventListener('submit',async e=>{e.preventDefault();const form=e.currentTarget,password=form.elements.password.value;form.reset();try{const result=await ctx.api('/api/economysuite/tournament/reauth',{password});reauth=result.token;document.querySelector('#tw-reauth').close();ctx.status(ctx.t('Ověřeno. Nyní můžeš provést změnu.','Verified. You can now make the change.'),false);}catch(f){ctx.status(f.message,true);}});
  }
  function refreshLive(){const host=document.querySelector('#tw-live');if(host){const focus=document.activeElement?.dataset.match,scroll=host.querySelector('.tw-bracket')?.scrollLeft||0;host.innerHTML=renderLive();bindLive();const board=host.querySelector('.tw-bracket');if(board)board.scrollLeft=scroll;if(focus)host.querySelector(`[data-match="${CSS.escape(focus)}"]`)?.focus();}}
  async function poll(){if(loading||document.hidden)return;loading=true;try{await load(ctx.api);refreshLive();if(ctx.admin&&!state.admin){reauth='';const admin=document.querySelector('#tw-admin');if(admin)admin.innerHTML=adminPanel();}const stale=document.querySelector('#tw-form-stale'),form=document.querySelector('[data-tw-form]');if(stale&&form)stale.textContent=JSON.parse(form.dataset.stamp).revision!==state.snapshot?.revision?ctx.t('Turnaj se změnil. Před úpravou obnov formuláře.','Tournament changed. Refresh forms before editing.'):'';const ops=JSON.stringify(state.operations);if(lastOperations&&ops!==lastOperations){const latest=state.operations?.[0];if(latest&&latest.state!=='pending')ctx.status(plain(latest.result)||latest.state,latest.state!=='complete');}lastOperations=ops;}catch{if(state)state.fresh=false;refreshLive();}finally{document.querySelectorAll('[data-tw-form] button').forEach(b=>b.disabled=!state?.fresh||b.dataset.phaseDisabled==='true');loading=false;}}
  function bind(context){ctx={...ctx,...context};bindLive();if(ctx.admin)bindAdmin();if(!resizeBound){root.addEventListener('resize',drawConnections);resizeBound=true;}if(pollTimer)clearInterval(pollTimer);if(clockTimer)clearInterval(clockTimer);pollTimer=setInterval(poll,2000);clockTimer=setInterval(updateClock,1000);}
  const api={render,load,bind,head,bracket,skin,nextAction,standings};root.ESTournament=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
