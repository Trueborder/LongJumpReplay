(function (root) {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const plain = value => String(value || '').replace(/[&§][0-9a-fk-or]/gi,'');
  const skin = value => /^https:\/\/textures\.minecraft\.net\/texture\/[a-f0-9]{32,64}$/.test(value||'') ? value : '';
  const phases = {DRAFT:['Příprava','Draft'],REGISTRATION:['Registrace otevřena','Registration open'],LOCKED:['Přesun do lobby','Lobby transfer'],ROUND_READY:['Kolo připraveno','Round ready'],ROUND_ACTIVE:['Hraje se','Playing'],INTERMISSION:['Pauza mezi koly','Intermission'],PAUSED:['Pozastaveno','Paused'],COMPLETED:['Dokončeno','Completed'],CANCELLED:['Zrušeno','Cancelled']};
  const stages = {Quarterfinal:['Čtvrtfinále','Quarterfinal'],Semifinal:['Semifinále','Semifinal'],Final:['Finále','Final'],Bronze:['O třetí místo','Third place']};
  const matchStates={PENDING:['Čeká','Waiting'],RUNNING:['Hraje se','Playing'],ADMIN_DECISION:['Rozhodnutí admina','Admin decision'],COMPLETE:['Dohráno','Finished']};
  const destructive = new Set(['cancel','forcewin','rematch','disqualify','remove','substitute','remove_prize','clear_prizes','preset','announce']);
  let state=null,ctx=null,pollTimer=null,clockTimer=null,busy=false,loading=false,selectedHistory='',lastOperations='',serverOffset=0,resizeBound=false,adminSection='rules',liveSignature='';
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
    return `<section class="tw-hero"><div><p class="es-eyebrow">PANTHEON / PvP</p><h2>${esc(t(...(phases[view.state]||['Aréna čeká','The arena awaits'])))}</h2><p>${view.size} ${esc(t('hráčů','players'))} · BO${view.best_of} · ${esc(view.policy==='SAME'?view.mode:t('Více módů','Multiple modes'))}</p></div><div class="tw-live ${state.fresh?'':'is-stale'}"><span>${esc(state.fresh?t('● Živě','● Live'):t('○ Server neodpovídá — pouze náhled','○ Server offline — read only'))}</span><small>${esc(t('Aktualizováno','Updated'))}: ${state.synced_at?new Date(state.synced_at*1000).toLocaleTimeString(t('cs-CZ','en-GB'),{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—'}</small><strong data-tw-countdown></strong></div></section>
      ${!historical?`<section class="es-panel tw-own"><div><small>${esc(t('TVŮJ TURNAJ','YOUR TOURNAMENT'))}</small><h3>${esc(joined?p.name:t('Ještě nejsi přihlášen/a','You have not joined'))}</h3><p>${esc(opponent?t('Soupeř: ','Opponent: ')+opponent.name:joined?(view.waitlist||[]).some(p=>p.uuid===own)?t('Jsi na čekací listině.','You are on the waiting list.'):t('Sleduj přípravu svého dalšího zápasu.','Watch for your next match.'):!own?t('Pro registraci nejprve propoj účet s Minecraftem.','Pair your Minecraft account to register.'):!online?t('Pro registraci se přihlas v Minecraftu.','Sign in to Minecraft to register.'):s.state==='REGISTRATION'?t('Registrace je otevřená — přidej se.','Registration is open — join in.'):t('Registrace zatím není otevřená.','Registration is not open yet.'))}</p></div>${s.state==='REGISTRATION'?`<button class="es-primary" data-tw-action="${joined?'leave':'join'}" ${!state.fresh||!own||!online?'disabled':''}>${esc(joined?t('Odhlásit se','Leave'):t('Přihlásit se','Join'))}</button>`:''}</section>`:''}
      <section class="es-panel tw-arena"><div class="tw-section-heading"><h2>${esc(t('Turnajový pavouk','Tournament bracket'))}</h2><span>${view.players.length}/${view.size} · ${esc(t('Kolo','Round'))} ${view.round||'—'}</span></div>${bracket(view,t,own)}</section>
      <div class="tw-detail-grid"><section class="es-panel"><h2>${esc(t('Odměny','Rewards'))}</h2><p class="tw-prize-total">${esc(plain(view.summary)||t('Odměny zatím nejsou nastavené','Rewards not set yet'))}</p>${[...new Set((view.prizes||[]).map(p=>p.place))].map(place=>`<div class="tw-prize-row"><strong>${place===5?'5.–8.':place+'.'} ${esc(t('místo','place'))}</strong><span>${view.prizes.filter(p=>p.place===place).map(p=>esc(plain(p.description))).join(' · ')}</span></div>`).join('')}<p class="es-muted">${esc(t('Výhry najdeš po turnaji v /mailbox.','Your prizes arrive in /mailbox after the tournament.'))}</p></section><section class="es-panel"><h2>${esc(t('Účastníci a čekatelé','Players and waiting list'))}</h2>${[...view.players,...view.waitlist].map(p=>`<div class="tw-roster">${head(p)}<strong>${esc(p.name)}</strong><span>${esc(view.waitlist.some(w=>w.uuid===p.uuid)?t('Čekatel','Waiting list'):p.online?t('Online','Online'):t('Offline','Offline'))}</span></div>`).join('')||`<p>${esc(t('Zatím nikdo.','No players yet.'))}</p>`}</section></div>
      ${admin&&state.admin&&!historical?`<section class="tw-next"><div><small>${esc(t('DALŠÍ FÁZE','NEXT PHASE'))}</small><strong>${esc(nextAction(s,t).label)}</strong><p>${esc(s.problems?.join(' · ')||t('Každý zásah znovu ověří herní server.','Every change is validated by the game server.'))}</p></div><button class="es-primary" data-tw-action="advance" ${!state.fresh||nextAction(s,t).disabled?'disabled':''}>${esc(t('Pokračovat','Continue'))} →</button></section>`:''}
      <details class="es-panel tw-history" data-disclosure="history"><summary>${esc(t('Historie turnajů','Tournament history'))}</summary><select id="tw-history" aria-label="${esc(t('Turnaj','Tournament'))}"><option value="">${esc(t('Aktuální turnaj','Current tournament'))}</option>${(state.history||[]).map(h=>`<option value="${esc(h.id)}" ${selectedHistory===h.id?'selected':''}>${esc(h.id.slice(0,8))} · ${h.size} · ${esc(t(...(phases[h.state]||['Turnaj','Tournament'])))}</option>`).join('')}</select></details>
      ${(state.operations||[]).length?`<details class="es-panel tw-operation-log" data-disclosure="operations"><summary>${esc(t('Poslední požadavky','Recent requests'))}</summary>${(state.operations||[]).slice(0,5).map(o=>`<p data-operation="${esc(o.id)}"><strong>${esc(o.action)}</strong> · ${esc(o.state)} — ${esc(plain(o.result||t('Čeká na potvrzení serveru','Waiting for server confirmation')))}</p>`).join('')}</details>`:''}`;
  }
  function adminStatus() {
    const s=state?.snapshot,{t}=ctx;if(!s||!state.admin)return '';
    const next=nextAction(s,t);
    return '<div class="tw-admin-state"><div><strong>'+esc(t(...(phases[s.state]||['Příprava','Draft'])))+'</strong><span>'+s.players.length+'/'+s.size+' · BO'+s.best_of+' · '+esc(s.automatic?t('Automaticky','Automatic'):t('Ručně','Manual'))+'</span></div><a href="/economysuite/tournament">'+esc(t('Otevřít pavouka','View bracket'))+' ↗</a></div><section class="tw-next"><div><small>'+esc(t('DALŠÍ FÁZE','NEXT PHASE'))+'</small><strong>'+esc(next.label)+'</strong><p>'+esc(plain(s.problems?.join(' · '))||t('Změny potvrzuje herní server.','Changes are confirmed by the game server.'))+'</p></div><button class="es-primary" data-tw-action="advance" '+(!state.fresh||next.disabled?'disabled':'')+'>'+esc(next.disabled?t('Čeká se','Waiting'):next.label)+' →</button></section>';
  }
  function adminPanel() {
    const {t}=ctx,s=state?.snapshot;
    if(!state?.admin)return '<section class="es-panel"><h2>'+esc(t('Nemáš přístup do administrace','Administration access denied'))+'</h2></section>';
    if(!s)return '<section class="es-panel tw-empty"><h2>'+esc(t('Čekáme na herní server','Waiting for the game server'))+'</h2></section>';
    const live=!!s.id&&!['COMPLETED','CANCELLED'].includes(s.state),editable=!live||['DRAFT','REGISTRATION'].includes(s.state),canSeed=live&&editable;
    const labels={SAME:t('Společný mód','Shared mode'),RANDOM:t('Náhodné módy','Random modes'),MANUAL:t('Ruční výběr','Manual selection'),true:t('Ano','Yes'),false:t('Ne','No'),coins:t('Coiny','Coins'),tokens:t('Tokeny','Tokens'),items:t('Předměty','Items'),keys:t('Klíče','Keys'),cosmetics:t('Kosmetika','Cosmetics'),mod:t('MOD předměty','MOD items')};
    const options=(list,value)=>list.map(v=>{const [id,label]=Array.isArray(v)?v:[v,labels[v]||v];return '<option value="'+esc(id)+'" '+(String(id)===String(value)?'selected':'')+'>'+esc(label)+'</option>';}).join('');
    const field=(key,label,value='',type='text')=>'<label>'+esc(label)+'<input name="'+esc(key)+'" type="'+type+'" value="'+esc(value)+'" '+(type==='number'?'min="0" step="1"':'')+' required></label>';
    const select=(key,label,list,value)=>'<label>'+esc(label)+'<select name="'+esc(key)+'">'+options(list,value)+'</select></label>';
    const hidden=(key,value)=>'<input type="hidden" name="'+esc(key)+'" value="'+esc(value)+'">';
    const form=(action,label,fields,disabled=false)=>'<form class="tw-form" data-tw-form="'+action+'" data-stamp="'+esc(JSON.stringify(stamp(s)))+'">'+fields+'<button type="submit" '+(disabled?'disabled':'')+'>'+esc(label)+'</button></form>';
    const action=(a,label,payload={},disabled=false)=>form(a,label,Object.entries(payload).map(([k,v])=>hidden(k,v)).join(''),disabled);
    const section=(id,label,body)=>'<section class="es-panel tw-admin-section" id="tw-section-'+id+'" aria-labelledby="tw-tab-'+id+'" '+(adminSection!==id?'hidden':'')+'><h2>'+esc(label)+'</h2>'+body+'</section>';
    const createNote=!live?'<p class="tw-notice">'+esc(t('Nejprve vytvoř turnaj v Pravidlech.','Create a tournament in Rules first.'))+'</p>':'';
    const lockedNote=!editable?'<p class="tw-notice">'+esc(t('Registrace je uzamčená. Pravidla a nasazení už nelze měnit.','Registration is locked. Rules and seeding can no longer change.'))+'</p>':'';
    const places=Array.from({length:s.size===8?5:s.size},(_,i)=>[String(i+1),i===4?'5.–8.':(i+1)+'. '+t('místo','place')]);
    const enrolled=[...s.players,...s.waitlist],available=s.online.filter(p=>!enrolled.some(e=>e.uuid===p.uuid));
    const players=enrolled.map(p=>{
      const waiting=s.waitlist.some(w=>w.uuid===p.uuid),index=s.players.findIndex(v=>v.uuid===p.uuid);
      return '<div class="tw-admin-player" data-player-row="'+esc(p.uuid)+'"><span class="tw-seed">'+(waiting?'↳':index+1)+'</span>'+head(p)+'<div class="tw-player-identity"><strong>'+esc(p.name)+'</strong><small>'+esc(waiting?t('Čekatel','Waiting list'):p.online?t('Online','Online'):t('Offline','Offline'))+'</small></div><div class="tw-row-actions">'+(!waiting?action('seed',t('↑ Výš','↑ Up'),{player:p.uuid,direction:-1},!canSeed||index===0)+action('seed',t('↓ Níž','↓ Down'),{player:p.uuid,direction:1},!canSeed||index===s.players.length-1):'')+(!waiting?'<details class="tw-inline-details"><summary>'+esc(t('Nahradit','Replace'))+'</summary>'+form('substitute',t('Potvrdit náhradu','Confirm replacement'),hidden('player',p.name)+select('replacement',t('Náhradník','Replacement'),available.map(v=>v.name)),!available.length||!canSeed)+'</details>':'')+action('remove',t('Odebrat','Remove'),{player:p.name},!canSeed)+(!editable&&!waiting?action('disqualify',t('Diskvalifikovat','Disqualify'),{player:p.name}):'')+'</div></div>';
    }).join('')||'<p class="es-muted">'+esc(t('Zatím nikdo. Přidej hráče nebo otevři registraci.','No entrants yet. Add a player or open registration.'))+'</p>';
    const tabs=[['rules',t('Pravidla','Rules')],['players',t('Hráči','Players')+' · '+enrolled.length],['matches',t('Zápasy','Matches')],['rewards',t('Odměny','Rewards')],['times',t('Časy','Timing')],['controls',t('Správa','Controls')]];
    const rules=lockedNote+form(live?'rules':'create',live?t('Uložit pravidla','Save rules'):t('Vytvořit turnaj','Create tournament'),select('size',t('Počet hráčů','Players'),['2','4','8'],s.size)+select('best_of',t('Formát','Format'),[['1','BO1'],['3','BO3']],s.best_of)+select('policy',t('Výběr módů','Mode policy'),['SAME','RANDOM','MANUAL'],s.policy)+select('mode',t('Společný mód','Shared mode'),s.modes,s.mode),!editable||s.celebrating)+'<p class="tw-policy-hint">'+esc(t('Společný: jeden mód pro všechny. Náhodný: výběr z poolu. Ruční: nastavíš každý zápas.','Shared: one mode for everyone. Random: choose from the pool. Manual: configure each match.'))+'</p>'+form('pool',t('Uložit výběr módů','Save mode pool'),'<fieldset class="tw-mode-pool"><legend>'+esc(t('Módy pro náhodný výběr','Random mode pool'))+'</legend>'+s.modes.map(mode=>'<label><input type="checkbox" name="modes" value="'+esc(mode)+'" '+(s.pool.includes(mode)?'checked':'')+'>'+esc(mode)+'</label>').join('')+'</fieldset>',!live||!editable)+form('seeding',t('Uložit nasazení','Save seeding'),select('random',t('Náhodné nasazení hráčů','Random player seeding'),['true','false'],String(s.random_seeding)),!canSeed);
    const roster=createNote+lockedNote+'<div class="tw-player-list">'+players+'</div>'+(live?form('add',t('Přidat hráče','Add player'),select('player',t('Další online hráč','Another online player'),available.map(p=>p.name)),!canSeed||!available.length):'');
    const matches=s.matches.map(m=>{
      const names=[m.first,m.second].map(id=>s.players.find(p=>p.uuid===id)?.name).filter(Boolean),pending=m.state==='PENDING';
      return '<article class="tw-match-settings"><header><strong>'+esc(t(...(stages[m.label]||['Zápas','Match'])))+' · '+esc(names.join(' × ')||t('Soupeři nejsou určeni','Players pending'))+'</strong><small>'+esc(m.id)+' · '+esc(m.state==='RUNNING'?t('Hraje se','Playing'):m.state==='COMPLETE'?t('Dohráno','Finished'):t('Čeká','Waiting'))+'</small></header>'+form('mode',t('Uložit mód','Save mode'),hidden('match',m.id)+select('mode',t('Mód','Mode'),s.modes,m.mode),!pending)+form('arena',t('Uložit arénu','Save arena'),hidden('match',m.id)+select('arena',t('Aréna','Arena'),[['',t('Automaticky','Automatic')],...s.arenas],m.arena),!pending)+'<details class="tw-inline-details"><summary>'+esc(t('Rozhodnutí a odveta','Decision and rematch'))+'</summary>'+action('rematch',t('Odveta','Rematch'),{match:m.id})+form('forcewin',t('Určit vítěze','Force winner'),hidden('match',m.id)+select('player',t('Vítěz','Winner'),names),!names.length)+'</details></article>';
    }).join('')||'<p class="es-muted">'+esc(t('Zápasy vzniknou po uzamčení registrace. Pavouk je v kartě Turnaj.','Matches appear after registration closes. The bracket is in Tournament.'))+'</p>';
    const rewardRows=places.map(([place,label])=>'<div class="tw-reward-place"><header><strong>'+esc(label)+'</strong>'+action('remove_prize',t('Vymazat místo','Clear place'),{place,index:-1},!live||!s.prizes.some(p=>p.place===Number(place)))+'</header>'+ (s.prizes.filter(p=>p.place===Number(place)).map(p=>'<div class="tw-prize-edit"><span>'+esc(plain(p.description))+'</span>'+action('remove_prize',t('Odebrat','Remove'),{place:p.place,index:p.index},!live)+'</div>').join('')||'<small class="es-muted">'+esc(t('Bez odměny','No reward'))+'</small>')+'</div>').join('');
    const rewards=createNote+'<p class="tw-prize-total">'+esc(plain(s.summary)||t('Odměny zatím nejsou nastavené','Rewards not set yet'))+'</p>'+form('preset',t('Použít preset','Apply preset'),select('preset',t('Balíček odměn — nahradí současné','Reward bundle — replaces current'),s.presets.map(p=>[p.id,plain(p.name)+' · '+plain(p.summary)])),!live||!s.presets.length)+rewardRows+'<details class="tw-inline-details tw-add-reward"><summary>'+esc(t('+ Přidat odměnu','+ Add reward'))+'</summary>'+form('prize',t('Přidat měnu','Add currency'),select('place',t('Umístění','Place'),places)+select('type',t('Měna','Currency'),['coins','tokens'])+field('amount',t('Částka','Amount'),100,'number'),!live)+'<div class="tw-catalog-filters"><div class="tw-search-field"><label>'+esc(t('Hledat odměnu','Search rewards'))+'<input id="tw-search" type="search" aria-controls="tw-reward-suggestions" autocomplete="off" placeholder="'+esc(t('Název předmětu nebo klíče…','Item or key name…'))+'"></label><div id="tw-reward-suggestions" class="tw-reward-suggestions" role="group" aria-label="'+esc(t('Navržené odměny','Suggested rewards'))+'" hidden></div></div><label>'+esc(t('Kategorie','Category'))+'<select id="tw-category"><option value="">'+esc(t('Všechny','All'))+'</option>'+options([...new Set(s.catalog.map(p=>p.category))])+'</select></label></div>'+form('catalog_prize',t('Přidat předmět','Add item'),select('place',t('Umístění','Place'),places)+'<label>'+esc(t('Předmět','Item'))+'<select id="tw-catalog" name="id">'+s.catalog.map(p=>'<option value="'+esc(p.id)+'" data-category="'+esc(p.category)+'">'+esc(plain(p.name))+' · '+p.amount+'</option>').join('')+'</select></label>'+field('count',t('Počet kopií','Copies'),1,'number')+hidden('catalog_revision',s.catalog_revision),!live||!s.catalog.length)+'</details>'+action('clear_prizes',t('Vymazat všechny odměny','Clear all rewards'),{},!live||!s.prizes.length);
    const timeLabels={'inter-match-delay-seconds':t('Pauza mezi zápasy','Inter-match delay'),'reconnect-grace-seconds':t('Lhůta na návrat','Reconnect grace'),'sudden-death-seconds':t('Náhlá smrt','Sudden death'),'waiting-reminder-seconds':t('Připomenutí čekajícím','Waiting reminder')};
    const times=createNote+'<p class="es-muted">'+esc(t('Hodnoty jsou v sekundách. Změna neovlivní právě běžící odpočet.','Values are seconds. Changes do not alter an active countdown.'))+'</p><div class="tw-time-grid">'+Object.entries(s.times).map(([key,value])=>form('time',t('Uložit','Save'),hidden('key',key)+field('seconds',(timeLabels[key]||key)+' (s)',value,'number'),!live)).join('')+'</div>'+form('automatic',t('Uložit pokračování','Save progression'),select('enabled',t('Automaticky pokračovat','Advance automatically'),['true','false'],String(s.automatic)),!live);
    const controls=createNote+'<h3>'+esc(t('Oznámení hráčům','Player announcement'))+'</h3><div class="tw-row-actions">'+action('announce',t('Náhled','Preview'),{preview:true},s.state!=='REGISTRATION')+action('announce',t('Zveřejnit ve hře','Publish in game'),{preview:false},s.state!=='REGISTRATION')+'</div><h3>'+esc(t('Zásahy do turnaje','Tournament controls'))+'</h3><div class="tw-row-actions">'+['pause','recover','cleanup','cancel'].map((a,i)=>action(a,t(...[['Pozastavit','Pause'],['Obnovit','Resume'],['Uklidit arény','Clean arenas'],['Zrušit turnaj','Cancel tournament']][i]),{},!live&&a!=='cleanup')).join('')+'</div><h3>'+esc(t('Kontrola připravenosti','Readiness checks'))+'</h3><ul>'+ (s.problems.map(p=>'<li>'+esc(plain(p))+'</li>').join('')||'<li>'+esc(t('Žádné zjištěné problémy. Omezení dalších pluginů ověří živý test.','No detected problems. A live test checks other plugins.'))+'</li>')+'</ul><details class="tw-inline-details"><summary>'+esc(t('Poslední změny','Recent changes'))+'</summary><div class="tw-operation-log">'+(state.operations||[]).slice(0,5).map(o=>'<p><strong>'+esc(o.action)+'</strong> · '+esc(o.state)+'<small>'+esc(plain(o.result||''))+'</small></p>').join('')+'</div></details>';
    return '<div id="tw-admin-status">'+adminStatus()+'</div><div class="tw-admin-toolbar"><nav class="tw-admin-tabs" aria-label="'+esc(t('Nastavení turnaje','Tournament settings'))+'">'+tabs.map(([id,label])=>'<button type="button" id="tw-tab-'+id+'" data-admin-section="'+id+'" aria-pressed="'+(adminSection===id)+'" aria-controls="tw-section-'+id+'">'+esc(label)+'</button>').join('')+'</nav><button type="button" data-refresh-admin>'+esc(t('Obnovit','Refresh'))+' ↻</button></div><p id="tw-form-stale" role="status"></p><div class="tw-admin-panels">'+section('rules',t('Pravidla turnaje','Tournament rules'),rules)+section('players',t('Hráči a nasazení','Players and seeding'),roster)+section('matches',t('Nastavení zápasů','Match settings'),matches)+section('rewards',t('Odměny','Rewards'),rewards)+section('times',t('Časy a automatika','Timing and automation'),times)+section('controls',t('Správa a diagnostika','Controls and diagnostics'),controls)+'</div>';
  }
  function render(context) {
    ctx={...ctx,...context};
    return context.admin?'<div id="tw-admin">'+adminPanel()+'</div>':'<div id="tw-live">'+renderLive()+'</div><dialog id="tw-match-detail" class="tw-dialog"><div id="tw-match-content"></div><form method="dialog"><button>'+esc(context.t('Zavřít','Close'))+'</button></form></dialog>';
  }
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
      const body={...expected,action,payload,idempotency_key:crypto.randomUUID(),confirm:true};
      await ctx.api('/api/economysuite/tournament/action',body);
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
      document.querySelector('#tw-match-content').innerHTML=`<h2>${esc(ctx.t(...(stages[m.label]||['Zápas','Match'])))}</h2>${playerLine(m.first,s,m.first_score,m.winner,state.uuid)}${playerLine(m.second,s,m.second_score,m.winner,state.uuid)}<p>${esc(m.mode)} · ${esc(m.arena)} · ${esc(ctx.t(...(matchStates[m.state]||['Čeká','Waiting'])))}</p><p>${esc(ctx.t('Sledování ve hře: /tournament spectate','Watch in Minecraft: /tournament spectate'))}</p>`;
      document.querySelector('#tw-match-detail').showModal();drawHeads();
    });drawHeads();drawConnections();updateClock();
  }
  function bindAdmin() {
    const status=document.querySelector('#tw-admin-status');if(status)status.dataset.rendered=adminStatus();
    document.querySelector('[data-refresh-admin]')?.addEventListener('click',()=>{document.querySelector('#tw-admin').innerHTML=adminPanel();bindAdmin();});
    document.querySelectorAll('[data-admin-section]').forEach(button=>button.addEventListener('click',()=>{
      adminSection=button.dataset.adminSection;
      document.querySelectorAll('[data-admin-section]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
      document.querySelectorAll('.tw-admin-section').forEach(panel=>panel.hidden=panel.id!=='tw-section-'+adminSection);
      drawHeads();
    }));
    document.querySelectorAll('#tw-admin-status [data-tw-action]').forEach(b=>b.onclick=()=>send(b.dataset.twAction));
    document.querySelectorAll('[data-tw-form]').forEach(form=>{const button=form.querySelector('button');button.dataset.phaseDisabled=String(button.disabled);form.addEventListener('submit',e=>{
      e.preventDefault();const payload=Object.fromEntries(new FormData(form));if(form.dataset.twForm==='pool')payload.modes=new FormData(form).getAll('modes').join(',');for(const k of ['preview','enabled','random'])if(k in payload)payload[k]=payload[k]==='true';send(form.dataset.twForm,payload,JSON.parse(form.dataset.stamp));
    });});
    const search=document.querySelector('#tw-search'),category=document.querySelector('#tw-category'),suggestions=document.querySelector('#tw-reward-suggestions');
    const catalogButton=document.querySelector('[data-tw-form="catalog_prize"] button'),catalogBlocked=catalogButton?.dataset.phaseDisabled==='true';
    const filter=(show=true)=>{
      const list=catalogMatches(state.snapshot.catalog,search?.value||'',category?.value||''),ids=new Set(list.map(p=>p.id));
      document.querySelectorAll('#tw-catalog option').forEach(o=>{o.hidden=!ids.has(o.value);o.disabled=o.hidden;});
      const select=document.querySelector('#tw-catalog');
      if(select&&select.selectedOptions[0]?.disabled)select.value=[...select.options].find(o=>!o.disabled)?.value||'';
      if(suggestions){
        suggestions.hidden=!show||!search?.value.trim();
        suggestions.innerHTML=list.slice(0,8).map(p=>'<button type="button" data-reward-id="'+esc(p.id)+'"><strong>'+esc(plain(p.name))+'</strong><small>'+esc(p.amount+' × · '+({keys:ctx.t('Klíče','Keys'),items:ctx.t('Předměty','Items'),coins:ctx.t('Coiny','Coins'),cosmetics:ctx.t('Kosmetika','Cosmetics'),mod:'MOD'}[p.category]||p.category))+'</small></button>').join('')||'<p role="status">'+esc(ctx.t('Žádná odpovídající odměna.','No matching reward.'))+'</p>';
      }
      if(catalogButton){catalogButton.dataset.phaseDisabled=String(catalogBlocked||!list.length);catalogButton.disabled=!state.fresh||catalogButton.dataset.phaseDisabled==='true';}
    };
    search?.addEventListener('input',()=>filter());category?.addEventListener('change',()=>filter());
    search?.addEventListener('keydown',e=>{
      if(e.key==='ArrowDown'&&!suggestions?.hidden){e.preventDefault();suggestions.querySelector('button')?.focus();}
      if(e.key==='Escape'&&suggestions){suggestions.hidden=true;}
    });
    suggestions?.addEventListener('click',e=>{
      const button=e.target.closest('[data-reward-id]');if(!button)return;
      const item=state.snapshot.catalog.find(p=>p.id===button.dataset.rewardId);if(!item)return;
      search.value=plain(item.name);filter(false);document.querySelector('#tw-catalog').value=item.id;search.focus();
    });
    suggestions?.addEventListener('keydown',e=>{
      const buttons=[...suggestions.querySelectorAll('button')],index=buttons.indexOf(document.activeElement);
      if(e.key==='ArrowDown'){e.preventDefault();buttons[Math.min(index+1,buttons.length-1)]?.focus();}
      if(e.key==='ArrowUp'){e.preventDefault();if(index<=0)search.focus();else buttons[index-1]?.focus();}
      if(e.key==='Escape'){e.preventDefault();suggestions.hidden=true;search.focus();}
    });
    filter(false);
    document.querySelectorAll('[data-tw-form] button').forEach(b=>b.disabled=!state.fresh||b.dataset.phaseDisabled==='true');
    drawHeads();
  }
  function refreshLive(){
    const host=document.querySelector('#tw-live');if(!host)return;
    const signature=JSON.stringify([state.snapshot,state.history,state.uuid,state.player_online,state.fresh,selectedHistory,ctx.t('cs','en')]);
    if(signature===liveSignature){updateClock();return;}liveSignature=signature;
    const focus=document.activeElement?.dataset.match,scroll=host.querySelector('.tw-bracket')?.scrollLeft||0;
    const open=[...host.querySelectorAll('details[open][data-disclosure]')].map(e=>e.dataset.disclosure);
    host.innerHTML=renderLive();bindLive();
    host.querySelectorAll('details[data-disclosure]').forEach(e=>e.open=open.includes(e.dataset.disclosure));
    const board=host.querySelector('.tw-bracket');if(board)board.scrollLeft=scroll;
    if(focus)host.querySelector('[data-match="'+CSS.escape(focus)+'"]')?.focus();
  }
  async function poll(){
    if(loading||document.hidden)return;loading=true;
    try{
      await load(ctx.api);refreshLive();
      if(ctx.admin&&!state.admin){const admin=document.querySelector('#tw-admin');if(admin)admin.innerHTML=adminPanel();}
      const status=document.querySelector('#tw-admin-status');
      if(status){const html=adminStatus();if(status.dataset.rendered!==html){status.innerHTML=html;status.dataset.rendered=html;status.querySelectorAll('[data-tw-action]').forEach(b=>b.onclick=()=>send(b.dataset.twAction));}}
      const stale=document.querySelector('#tw-form-stale'),form=document.querySelector('[data-tw-form]');
      if(stale&&form){
        const expected=JSON.parse(form.dataset.stamp),current=stamp(state.snapshot);
        const changed=expected.revision!==current.revision||expected.instance!==current.instance||expected.tournament_id!==current.tournament_id;
        stale.textContent=changed?ctx.t('Turnaj se změnil. Klikni na Obnovit; rozepsané hodnoty zůstanou do té doby zachované.','Tournament changed. Select Refresh; your draft values are preserved until then.'):'';
        stale.dataset.changed=String(changed);
      }
      const ops=JSON.stringify(state.operations);
      if(lastOperations&&ops!==lastOperations){const latest=state.operations?.[0];if(latest&&latest.state!=='pending')ctx.status(plain(latest.result)||latest.state,latest.state!=='complete');}
      lastOperations=ops;
    }catch{if(state)state.fresh=false;refreshLive();document.querySelectorAll('#tw-admin-status button').forEach(b=>b.disabled=true);}
    finally{document.querySelectorAll('[data-tw-form] button').forEach(b=>b.disabled=!state?.fresh||b.dataset.phaseDisabled==='true');loading=false;}
  }
  function bind(context){
    ctx={...ctx,...context};bindLive();if(ctx.admin)bindAdmin();
    if(!resizeBound){root.addEventListener('resize',drawConnections);resizeBound=true;}
    if(pollTimer)clearInterval(pollTimer);if(clockTimer)clearInterval(clockTimer);
    pollTimer=setInterval(poll,2000);clockTimer=setInterval(updateClock,1000);
  }
  const normalizeSearch=value=>plain(value).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase().trim();
  function catalogMatches(catalog,query='',category=''){
    const words=normalizeSearch(query).split(/\s+/).filter(Boolean);
    return (catalog||[]).filter(p=>(!category||p.category===category)&&words.every(word=>normalizeSearch(p.name).includes(word)));
  }
  const api={render,load,bind,head,bracket,skin,nextAction,standings,catalogMatches};root.ESTournament=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
