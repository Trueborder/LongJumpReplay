(() => {
  'use strict';
  let lastSignature = '';
  let config = null, rounds = [], submitting = false, filter = 'all', selection = { game: 'coin', currency: 'coins', stake: 100, choice: 'heads' }, uncertain = null, storageKey = '', displayed = '';
  const $ = id => document.getElementById(id);
  const sectorNames = [['Ztráta celé sázky','Full loss'],['−50 %','−50 %'],['−20 %','−20 %'],['Vrácení sázky','Stake returned'],['+20 %','+20 %'],['Dvojnásobek','Double']];
  const gameNames = { coin: ['Hod mincí', 'Coin toss'], dice: ['Kostky', 'Dice'], wheel: ['Kolo štěstí', 'Wheel'] };
  const issues = {
    disabled: ['Hry jsou vypnuté.', 'Games are disabled.'], expired: ['Požadavek vypršel. Sázka nebyla odečtena.', 'Request expired. No stake was debited.'],
    insufficient_funds: ['Nedostatek dostupných prostředků.', 'Insufficient available funds.'], debt: ['Peněženka je zablokovaná kvůli dluhu.', 'Your wallet is blocked by debt.'],
    cooldown: ['Mezi sázkami počkej alespoň pět sekund.', 'Wait at least five seconds between bets.'], unsafe_balance: ['Sázka nebo zůstatek přesahují bezpečný číselný rozsah.', 'The stake or balance exceeds the safe numeric range.'],
    invalid_input: ['Neplatné parametry sázky.', 'Invalid bet parameters.']
  };
  function readStored() { try { return JSON.parse(sessionStorage.getItem(storageKey) || 'null'); } catch { return null; } }
  function remember(value) { uncertain = value; if (value) sessionStorage.setItem(storageKey, JSON.stringify(value)); else sessionStorage.removeItem(storageKey); }
  async function load(api, account) {
    storageKey = 'es-game-' + account?.email + '-' + account?.link?.uuid;
    uncertain = readStored();
    [config, { rounds }] = await Promise.all([api('/api/economysuite/games/config'), api('/api/economysuite/games/rounds')]);
    if (uncertain && rounds.some(r => r.idempotency_key === uncertain.idempotency_key)) remember(null);
  }
  function render(c) {
    const { t, escape: e, number: n, date, panel, currencyIcon, account, table, row } = c;
    if (!account?.link) return c.empty();
    lastSignature = signature(account);
    const active = rounds.find(r => r.state === 'pending'), latest = rounds[0], detail = latest?.result ? JSON.parse(latest.result) : null;
    const choices = selection.game === 'coin' ? [['heads',t('Panna','Heads')],['tails',t('Orel','Tails')]] : selection.game === 'dice' ? [['10','10 %'],['25','25 %'],['50','50 %']] : [['', t('Šest výsledků','Six outcomes')]];
    if (!choices.some(([v]) => v === selection.choice)) selection.choice = choices[0][0];
    const odds = config?.tables[selection.game === 'dice' ? 'dice' + selection.choice : selection.game] || [];
    const minimum = selection.currency === 'coins' ? 100 : 10;
    const max = odds.length ? Number(BigInt(Number.MAX_SAFE_INTEGER) / BigInt(Math.max(...odds.map(o => o.factor)))) * 10 : 0;
    const balance = Number(account.snapshot?.[selection.currency] || 0), debt = Number(account.snapshot?.debt?.coins || 0) + Number(account.snapshot?.debt?.tokens || 0);
    const cooldown = latest && Date.now()/1000 - latest.created_at < 5;
    const valid = Number.isSafeInteger(selection.stake) && selection.stake >= minimum && selection.stake % 10 === 0 && selection.stake <= max && selection.stake <= balance;
    const enabled = config?.enabled && config.connected && config.supported && !active && !uncertain && !submitting && !cooldown && !debt && valid;
    const reason = !config?.enabled ? t('Hry jsou dostupné pouze v testovacím prostředí.', 'Games are available only in the test environment.') : !config.connected ? t('Server je odpojený.', 'Server disconnected.') : !config.supported ? t('Server nepodporuje tuto verzi her.', 'The server does not support this version of games.') : debt ? t(...issues.debt) : active ? t('Čeká na server', 'Waiting for server') : cooldown ? t(...issues.cooldown) : '';
    const resultText = (active || uncertain || submitting) ? t('Čeká na server', 'Waiting for server') : detail?.state === 'rejected' ? t(...(issues[detail.error] || issues.invalid_input)) : detail ? t('Vyhodnoceno', 'Evaluated') + ': ' + (latest.game === 'wheel' ? t(...sectorNames[Number(detail.outcome)]) : latest.game === 'coin' ? (detail.outcome === 'heads' ? t('Panna','Heads') : t('Orel','Tails')) : detail.outcome === 'win' ? t('V\u00fdhra','Win') : t('Prohra','Loss')) + ' · ' + n(latest.payout) + ' ' + latest.currency + ' · ' + t('Čistá změna: ', 'Net change: ') + n(latest.net) : t('Vyber hru a sázku.', 'Choose a game and stake.');
    const form = `<p>${e(t('Průměrná návratnost je 95 %. Jde o dlouhodobý matematický průměr, nikoli zaručený výsledek. Násobek zahrnuje původní vklad. Čistá změna = výplata − sázka.', 'Average return is 95%. This is a long-term mathematical average, not a guaranteed result. Multipliers include the original stake. Net change = payout − stake.'))}</p><form id="game-form" class="es-game-form"><label>${t('Hra','Game')}<select id="game-type">${Object.entries(gameNames).map(([id,name])=>`<option value="${id}" ${id===selection.game?'selected':''}>${e(t(...name))}</option>`).join('')}</select></label><label>${t('Měna','Currency')}<select id="game-currency"><option value="coins" ${selection.currency==='coins'?'selected':''}>Coins</option><option value="tokens" ${selection.currency==='tokens'?'selected':''}>Tokens</option></select></label><label>${t('Volba','Choice')}<select id="game-choice">${choices.map(([id,name])=>`<option value="${id}" ${id===selection.choice?'selected':''}>${e(name)}</option>`).join('')}</select></label><label>${t('Sázka','Stake')}<input id="game-stake" type="number" min="${minimum}" max="${Math.min(max,balance)}" step="10" value="${selection.stake}" required inputmode="numeric"></label><p>${currencyIcon(selection.currency)} ${t('Dostupný zůstatek','Available balance')}: ${n(balance)} ${selection.currency}. ${t('Minimum','Minimum')}: ${minimum}; ${t('krok','step')}: 10.</p><button id="game-bet" class="es-primary" type="submit" ${enabled?'':'disabled'}>${t('Vsadit','Bet')} ${n(selection.stake)} ${selection.currency}</button></form><p>${e(reason)}</p>${uncertain && !submitting?`<p>${e(t('Odpověď se nepodařilo ověřit. Obnov původní požadavek se stejným identifikátorem.', 'The response could not be verified. Recover the original request with the same identifier.'))}</p><button id="game-recover">${t('Obnovit původní sázku','Recover original bet')}</button>`:''}`;
    const visualGame = active?.game || uncertain?.game || selection.game;
    const waiting = Boolean(active || uncertain || submitting);
    const confirmed = !waiting && latest?.state === 'complete' && latest.game === visualGame;
    const fresh = confirmed && displayed !== latest.id;
    const phase = waiting ? 'waiting' : confirmed ? 'complete' : 'idle';
    // Waiting motion carries no outcome. Only the plugin acknowledgment supplies the face/roll/sector.
    const face = confirmed ? (visualGame === 'coin' ? (detail.outcome === 'heads' ? t('Panna','Heads') : t('Orel','Tails')) : String(detail.roll).padStart(2,'0')) : '?';
    const visual = `<div class="es-game-stage ${fresh?'is-revealing':''}" data-game="${visualGame}" data-phase="${phase}" aria-hidden="true">${visualGame === 'wheel' ? '<div class="es-wheel-wrap"><span class="es-wheel-pointer">&#9660;</span><div class="es-game-wheel" id="game-wheel"></div></div>' : `<div class="es-game-${visualGame}" id="game-piece">${e(face)}</div>`}</div>`;
    const shown = rounds.filter(r => filter==='all' || (r.state==='complete' && (filter==='wins'?r.net>0:filter==='losses'?r.net<0:r.net===0)));
    return panel(t('Hry','Games'),form + visual + table([t('V\u00fdsledek','Outcome'),t('Pravd\u011bpodobnost','Probability'),t('Celkov\u00e1 v\u00fdplata','Total payout')],odds.map((o,i)=>row([selection.game==='wheel'?`<span class="es-wheel-swatch" data-sector="${i}" aria-hidden="true"></span>`+e(t(...sectorNames[i])):e(i===0?t('V\u00fdhra','Win'):t('Prohra','Loss')),o.probability+' %',(o.factor/10)+'\u00d7 \u00b7 '+n(Number(BigInt(Number.isSafeInteger(selection.stake) && selection.stake >= 0 ? Math.floor(selection.stake/10) : 0)*BigInt(o.factor)))+' '+selection.currency]))) + `<p id="game-result" role="status" aria-live="polite">${e(resultText)}</p>`) + panel(t('Historie kol','Round history'),`<label>${t('Filtr','Filter')}<select id="game-filter">${[['all','Všechny','All'],['wins','Výhry','Wins'],['losses','Prohry','Losses'],['returned','Vrácené sázky','Returned stakes']].map(([id,cs,en])=>`<option value="${id}" ${filter===id?'selected':''}>${t(cs,en)}</option>`).join('')}</select></label>` + table([t('Hra','Game'),t('Měna','Currency'),t('Sázka','Stake'),t('Výplata','Payout'),t('Čistá změna','Net change'),t('Datum','Date'),t('Stav','State'),t('Identifikátor','Round ID')],shown.map(r=>row([e(t(...gameNames[r.game])),e(r.currency),n(r.stake),r.payout===null?'—':n(r.payout),r.net===null?'—':n(r.net),date(r.created_at),e(r.state==='pending'?t('Čeká na server','Waiting for server'):r.state==='complete'?t('Vyhodnoceno','Evaluated'):t(...(issues[JSON.parse(r.result || '{}').error] || issues.invalid_input))),e(r.id)]))) + `<button id="game-more" ${rounds.length % 100 !== 0 || !rounds.length?'hidden':''}>${t('Starší kola','Older rounds')}</button>`);
  }
  function bind(c) {
    const redraw = () => { c.render(); };
    ['type','currency','choice'].forEach(field => $('game-'+field)?.addEventListener('change', event => {
      selection[field==='type'?'game':field] = event.target.value;
      if(field==='currency')selection.stake=Math.max(selection.stake,selection.currency==='coins'?100:10);
      redraw(); $('game-'+field)?.focus();
    }));
    $('game-stake')?.addEventListener('input',event=>{selection.stake=Number(event.target.value); const input=event.target; const start=input.selectionStart; redraw(); $('game-stake')?.focus(); if(start!==null) $('game-stake').setSelectionRange(start,start);});
    $('game-filter')?.addEventListener('change',event=>{filter=event.target.value;redraw();$('game-filter')?.focus();});
    $('game-more')?.addEventListener('click',async()=>{try{const result=await c.api('/api/economysuite/games/rounds?before='+rounds.at(-1).cursor);rounds.push(...result.rounds);redraw();}catch(f){c.status(f.message,true);}});
    async function send(payload) {
      if(submitting)return;
      submitting=true;remember(payload);redraw();c.status(c.t('Čeká na server','Waiting for server'));
      try { const response=await c.api('/api/economysuite/games/rounds',payload);remember(null);rounds=[response.round,...rounds.filter(r=>r.id!==response.round.id)]; }
      catch(f){if(f.status && f.status<500)remember(null);c.status(f.message,true);}
      finally{submitting=false;redraw();}
    }
    $('game-form')?.addEventListener('submit',event=>{event.preventDefault();if($('game-bet').disabled)return;send({...selection,rules_version:config.rules_version,idempotency_key:crypto.randomUUID()});});
    $('game-recover')?.addEventListener('click',()=>send(uncertain));
    const latest=rounds[0];
    if(latest?.state==='complete') {
      const result=JSON.parse(latest.result);const fresh=displayed!==latest.id;displayed=latest.id;
      if(latest.game==='wheel' && $('game-wheel')) {
        const centers=[9,54,126,207,288,342];
        const wheel=$('game-wheel');const angle=1080-centers[Number(result.outcome)];
        if(fresh){ requestAnimationFrame(()=>{if(wheel.isConnected)wheel.style.transform=`rotate(${angle}deg)`;}); }
        else {wheel.style.transition='none';wheel.style.transform=`rotate(${angle}deg)`;}
      }
    }
  }
  function signature(account) {
    return JSON.stringify([config, rounds, account?.snapshot?.coins, account?.snapshot?.tokens, account?.snapshot?.debt, rounds[0] && Date.now()/1000-rounds[0].created_at<5]);
  }
  async function poll(c) {
    if (!config || submitting) return;
    const pending=rounds.find(r=>r.state==='pending');
    config=await c.api('/api/economysuite/games/config');
    if(pending) {
      const {round}=await c.api('/api/economysuite/games/rounds/'+pending.id);
      rounds=rounds.map(r=>r.id===round.id?round:r);
      if(round.state!=='pending') c.status(round.state==='complete'?c.t('Vyhodnoceno','Evaluated'):c.t(...(issues[JSON.parse(round.result || '{}').error] || issues.invalid_input)),round.state==='rejected');
    } else {
      const result=await c.api('/api/economysuite/games/rounds');
      const older=rounds.filter(r=>!result.rounds.some(n=>n.id===r.id));
      rounds=[...result.rounds,...older];
    }
    if(signature(c.account)!==lastSignature) {
      const focus=document.activeElement?.id;
      c.render();
      if(focus) $(focus)?.focus();
    }
  }
  window.ESGames={load,render,bind,poll};
})();
