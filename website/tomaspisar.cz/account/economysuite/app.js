(() => {
  'use strict';
  // Keyboard actions stay immediate; pointer motion never delays the action.
  document.addEventListener('keydown', () => { document.documentElement.dataset.motionInput = 'keyboard'; }, true);
  document.addEventListener('pointerdown', () => { document.documentElement.dataset.motionInput = 'pointer'; }, true);
  const $ = s => document.querySelector(s);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let lang = localStorage.getItem('es-language') === 'en' ? 'en' : 'cs';
  let account = null, packages = [], purchasesEnabled = false, orders = [], rankings = [], metric = 'playtime', purchaseFilter = 'paid', pendingPurchase = null, dailyClaimPending = false;
  let refreshBaseline = null, refreshStarted = 0, refreshOperation = '', finishRefresh = null;
  const feedback = window.LJR_FEEDBACK;
  const route = location.pathname.split('/')[2] || 'overview';
  const successfulOrder = route === 'purchases' && /^[a-f0-9-]{36}$/i.test(new URLSearchParams(location.search).get('order') || '') ? new URLSearchParams(location.search).get('order') : '';
  const names = { overview: ['Přehled', 'Overview'], statistics: ['Statistiky', 'Statistics'], progress: ['Postup', 'Progress'], appearance: ['Vzhled', 'Appearance'], games: ['Hry', 'Games'], store: ['Obchod', 'Store'], rank: ['Ranky', 'Ranks'], purchases: ['Nákupy', 'Purchases'], settings: ['Nastavení', 'Settings'], pair: ['Propojení účtu', 'Pair your account'] };
  Object.assign(names,{tournament:['Turnaj','Tournament'],'tournament-admin':['Turnaj-admin','Tournament admin']});
  const paths = {
    rank: '<path d="m3 7 4 3 5-7 5 7 4-3-2 13H5L3 7Zm2 9h14"/>',
    games: '<rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="8" cy="8" r="1"/><circle cx="16" cy="8" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="8" cy="16" r="1"/><circle cx="16" cy="16" r="1"/>',
    overview: '<rect x="4" y="4" width="6" height="6"/><rect x="14" y="4" width="6" height="6"/><rect x="4" y="14" width="6" height="6"/><rect x="14" y="14" width="6" height="6"/>',
    statistics: '<path d="M4 19V9m6 10V5m6 14v-7m4 7H2"/>', progress: '<path d="m4 12 5 5L20 6"/>',
    appearance: '<path d="m12 3 1.4 4.1L18 8.5l-4.1 1.4L12.5 14l-1.4-4.1L7 8.5l4.1-1.4L12 3Zm-6 9 .8 2.2L9 15l-2.2.8L6 18l-.8-2.2L3 15l2.2-.8L6 12Zm11 3 1 2.8 3 1-3 1L17 23l-1-3.2-3-1 3-1L17 15Z"/>',
    store: '<path d="M4 9h16l-1 11H5L4 9Zm3 0a5 5 0 0 1 10 0"/>', purchases: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3Zm3 5h6m-6 4h6"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/>'
  };
  const icon = name => `<svg class="es-icon" viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.overview}</svg>`;
  const currencyIcon = currency => currency === 'tokens'
    ? '<svg class="es-currency-icon es-amethyst" viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2 27 11 21 28H10L4 12Z"/><path d="m16 2-2 10 7 16M4 12l10 0 13-1M10 28l4-16"/></svg>'
    : '<svg class="es-currency-icon es-sunflower" viewBox="0 0 32 32" aria-hidden="true"><path class="stem" d="M16 18v12m0-5-6-3m6 4 6-4"/><g class="petals"><circle cx="16" cy="5" r="5"/><circle cx="25" cy="9" r="5"/><circle cx="25" cy="19" r="5"/><circle cx="7" cy="19" r="5"/><circle cx="7" cy="9" r="5"/></g><circle class="centre" cx="16" cy="14" r="6"/></svg>';
  const t = (cs, en) => lang === 'cs' ? cs : en;
  const number = value => new Intl.NumberFormat(lang === 'cs' ? 'cs-CZ' : 'en-GB').format(Number(value || 0));
  const money = value => new Intl.NumberFormat(lang === 'cs' ? 'cs-CZ' : 'en-GB', { style: 'currency', currency: 'CZK' }).format(Number(value) / 100);
  const date = value => value ? new Date(value * 1000).toLocaleString(lang === 'cs' ? 'cs-CZ' : 'en-GB') : '—';
  const strip = value => String(value || '').replace(/[&§][0-9a-fk-or]/gi, '');
  function chatPreview(value) {
    const palette = ['#000000','#0000aa','#00aa00','#00aaaa','#aa0000','#aa00aa','#ffaa00','#aaaaaa','#555555','#5555ff','#55ff55','#55ffff','#ff5555','#ff55ff','#ffff55','#ffffff'];
    let colour = '#ffffff', bold = false, italic = false;
    return String(value || '').split(/([&§][0-9a-fklmnor])/i).map(part => {
      if (/^[&§][0-9a-fklmnor]$/i.test(part)) { const code = part[1].toLowerCase(); if (/[0-9a-f]/.test(code)) { colour = palette[parseInt(code,16)]; bold = italic = false; } else if (code === 'l') bold = true; else if (code === 'o') italic = true; else if (code === 'r') { colour = '#ffffff'; bold = italic = false; } return ''; }
      return `<span style="color:${colour};font-weight:${bold ? 700 : 500};font-style:${italic ? 'italic' : 'normal'}">${escape(part)}</span>`;
    }).join('');
  }
  const preview = (type, entry) => chatPreview(`${entry?.value ?? entry?.display ?? ''}${type === 'prefix' ? ' ' : ''}${account.link.name}${type === 'color' ? t(': Ukázka zprávy', ': Example message') : ''}`);
  const status = (message, failed = false, kind = failed ? 'error' : 'info') => feedback?.toast[kind]?.(message);
  const mobileNavigation = matchMedia('(max-width: 650px)');
  const navigationDialog = $('#navigation-dialog');
  const menuToggle = $('#menu-toggle');
  const sidebar = $('.es-sidebar');
  const closeNavigation = () => { if (navigationDialog.open) navigationDialog.close(); };
  function positionNavigation() {
    closeNavigation();
    if (mobileNavigation.matches) $('#mobile-navigation-content').append(sidebar);
    else $('.es-layout').prepend(sidebar);
  }
  menuToggle.addEventListener('click', () => {
    navigationDialog.showModal();
    menuToggle.setAttribute('aria-expanded', 'true');
    document.body.classList.add('es-navigation-open');
    ($('#navigation [aria-current="page"]') || $('#close-navigation')).focus();
  });
  $('#close-navigation').addEventListener('click', closeNavigation);
  navigationDialog.addEventListener('click', event => {
    if (event.target !== navigationDialog) return;
    const bounds = navigationDialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) closeNavigation();
  });
  navigationDialog.addEventListener('close', () => {
    menuToggle.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('es-navigation-open');
    if (mobileNavigation.matches) menuToggle.focus();
    else $('#navigation [aria-current="page"]')?.focus();
  });
  mobileNavigation.addEventListener('change', positionNavigation);
  positionNavigation();
  const cookie = name => document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith(`${name}=`))?.split('=').slice(1).join('=') || '';
  const errors = { rank_delivery_unavailable: ['Rank zatím nelze bezpečně doručit. Správce musí aktualizovat server.', 'Rank delivery is not ready. The administrator must update the server.'], pair_required: ['Nejdřív propoj svůj Minecraft účet.', 'Pair your Minecraft account first.'], invalid_password: ['Heslo není správné.', 'The password is incorrect.'], pair_expired: ['Propojení vypršelo. Použij znovu /web link.', 'Pairing expired. Run /web link again.'], pending_delivery: ['Nejdřív dokonči čekající nákupy a doručení.', 'Finish pending checkouts and deliveries first.'], already_linked: ['Tento účet nebo hráč už je propojený.', 'This account or player is already linked.'], unavailable: ['Tato funkce zatím není dostupná.', 'This feature is not available yet.'], stripe_minimum: ['Stripe vy\u017Eaduje minim\u00E1ln\u00ED platbu 15 K\u010D. Zvol vy\u0161\u0161\u00ED bal\u00ED\u010Dek.', 'Stripe requires a minimum 15 CZK payment. Choose a larger package.'], invalid_confirmation: ['Potvrzení není platné.', 'The confirmation is invalid.'] };
  Object.assign(errors, {
    games_disabled: ['Hry jsou vypnuté.', 'Games are disabled.'],
    server_games_disabled: ['Hry jsou na serveru vypnuté.', 'Games are disabled on the server.'],
    server_offline: ['Server je odpojený. Sázka nebyla přijata.', 'Server disconnected. The bet was not accepted.'],
    unsupported_plugin: ['Server nepodporuje tuto verzi her.', 'The server does not support this version of games.'],
    round_busy: ['Počkej na dokončení kola a alespoň pět sekund mezi sázkami.', 'Wait for your round to finish and at least five seconds between bets.'],
    idempotency_conflict: ['Tento identifikátor patří jiné sázce. Obnov stránku.', 'This identifier belongs to a different bet. Reload the page.'],
    invalid_game_input: ['Neplatná sázka nebo volba. Zkontroluj minimum a násobky deseti.', 'Invalid stake or choice. Check the minimum and multiples of ten.']
  });
  async function api(path, data) {
    const response = await fetch(path, { method: data ? 'POST' : 'GET', credentials: 'include', headers: data ? { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(cookie('__Host-es-csrf')) } : {}, body: data ? JSON.stringify(data) : undefined });
    const result = await response.json();
    if (!response.ok) {
      const pair = errors[path.startsWith('/api/economysuite/games/') && result.error === 'invalid_input' ? 'invalid_game_input' : result.error];
      const failure = new Error(pair ? t(...pair) : result.error === 'tournament_error' ? String(result.message || '').slice(0,500) : t('Požadavek se nepodařilo dokončit. Zkus to znovu.', 'The request could not be completed. Please try again.'));
      failure.status = response.status; throw failure;
    }
    return result;
  }
  const panel = (title, content, cls = '') => `<section class="es-panel ${cls}"><h2>${escape(title)}</h2>${content}</section>`;
  const empty = () => panel(t('Tvůj hráčský účet začíná propojením.', 'Your player account starts with pairing.'), `<p>${escape(t('Přihlas se na Pantheon a spusť příkaz. Na webu potvrď hráče a poté dokonči propojení ve hře.', 'Sign in to Pantheon and run the command. Confirm your player on the website, then finish pairing in-game.'))}</p><code>/web link</code>`, 'es-empty');
  const waiting = () => panel(t('Čekáme na první synchronizaci.', 'Waiting for the first sync.'), `<p>${escape(t('Účet je propojený. Přehled se naplní, jakmile se připojí server.', 'Your account is paired. Your overview will populate when the server connects.'))}</p>`);
  const loading = () => `<div class="es-skeleton-grid" aria-label="${escape(t('Načítám obsah', 'Loading content'))}"><span class="es-skeleton es-skeleton-large"></span><span class="es-skeleton"></span><span class="es-skeleton"></span></div>`;
  const loadError = failure => panel(t('Data se nepodařilo načíst.', 'We could not load this dashboard.'), `<p>${escape(failure?.message || t('Zkontroluj připojení a zkus to znovu.', 'Check your connection and try again.'))}</p><button id="retry-load" class="es-primary es-retry" type="button">${t('Zkusit znovu', 'Try again')}</button>`, 'es-empty es-content-error');
  const table = (headers, rows) => `<div class="es-table-wrap"><table class="es-table"><thead><tr>${headers.map(h => `<th>${escape(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
  const row = cells => `<tr>${cells.map(c => `<td>${c}</td>`).join('')}</tr>`;
  const statNames = { playtime: ['Doba hraní (min)', 'Playtime (min)'], blocks_mined: ['Vytěžené bloky', 'Blocks mined'], blocks_placed: ['Položené bloky', 'Blocks placed'], mobs_killed: ['Zabití mobové', 'Mobs killed'], deaths: ['Úmrtí', 'Deaths'], crafted: ['Výroba', 'Crafting'], smelted: ['Tavení', 'Smelting'], fish_caught: ['Ulovené ryby', 'Fish caught'], breeding: ['Chov', 'Breeding'], trades: ['Obchody', 'Trades'], items_sold: ['Prodané předměty', 'Items sold'], items_bought: ['Koupené předměty', 'Items bought'], challenges_won: ['Vyhrané výzvy', 'Challenges won'], tasks_completed: ['Dokončené úkoly', 'Completed tasks'], crates_opened: ['Otevřené crates', 'Crates opened'], daily_claims: ['Denní odměny', 'Daily claims'], passive_job_coins: ['Výdělek z profese', 'Job income'], duel_wins: ['Výhry v duelech', 'Duel wins'], duel_losses: ['Prohry v duelech', 'Duel losses'], duel_draws: ['Remízy v duelech', 'Duel draws'], duel_damage: ['Poškození v duelech', 'Duel damage'] };
  const metricCard = (title, value, note, currency = '') => `<section class="es-panel es-metric"><div class="es-metric-heading">${currency ? currencyIcon(currency) : icon('statistics')}<small>${escape(title)}</small></div><strong>${number(value)}</strong><span class="es-label">${escape(note)}</span></section>`;
  function xpSources() {
    const sources = [
      [t('Denn\u00ed questy', 'Daily quests'), t('+35 XP za dokon\u010den\u00fd denn\u00ed quest', '+35 XP per completed daily quest')],
      [t('T\u00fddenn\u00ed questy', 'Weekly quests'), t('+180 XP za dokon\u010den\u00fd t\u00fddenn\u00ed quest', '+180 XP per completed weekly quest')],
      [t('Achievementy a v\u00fdzvy', 'Achievements and challenges'), t('+75 a\u017e +20 XP podle odm\u011bny', '+75 to +20 XP depending on the reward')],
      [t('Profesn\u00ed \u00fakoly', 'Job tasks'), t('+60 a\u017e v\u00edce XP podle kapitoly', '+60 XP or more depending on the chapter')]
    ];
    return '<div class="es-xp-sources"><div class="es-section-label">' + escape(t('Jak z\u00edskat XP', 'Ways to earn XP')) + '</div><ul>' + sources.map(source => '<li><strong>' + escape(source[0]) + '</strong><span>' + escape(source[1]) + '</span></li>').join('') + '</ul><p class="es-muted">' + escape(t('XP z\u00edsk\u00e1\u0161 hran\u00edm na serveru. Aktivita na webu sama o sob\u011b XP nep\u0159id\u00e1v\u00e1.', 'You earn XP by playing on the server. Website activity itself does not add XP.')) + '</p></div>';
  }
  function currentTasks(snapshot) {
    return ['daily', 'weekly'].map(period => {
      const progress = snapshot.progress || {};
      const tasks = progress.tasks_version === 2 && Array.isArray(progress[period]) ? progress[period] : [];
      const title = period === 'daily' ? t('Denní úkoly', 'Daily tasks') : t('Týdenní úkoly', 'Weekly tasks');
      const cycle = progress.cycles?.[period];
      return '<div class="es-subsection"><div class="es-section-label">' + escape(title) + (cycle ? '<span>' + escape(t('Období: ', 'Cycle: ') + cycle) + '</span>' : '') + '</div>' +
        (tasks.length ? table([t('Úkol', 'Task'), t('Postup', 'Progress'), t('Odměna', 'Reward'), t('Stav', 'State')], tasks.map(task => row([escape(strip(task.name || task.id)), number(task.progress) + ' / ' + number(task.target), number(task.reward_coins) + ' coins · ' + number(task.points) + ' ' + t('bodů', 'points'), task.complete ? t('Dokončeno', 'Complete') : t('Probíhá', 'In progress')]))) : '<p class="es-muted">' + escape(t('Čeká na synchronizaci denních a týdenních úkolů z aktualizovaného serveru.', 'Waiting for daily and weekly tasks from the updated server.')) + '</p>') + '</div>';
    }).join('');
  }
  function jobTask(snapshot) {
    const job = snapshot.job || {};
    const task = snapshot.job_task || {};
    const tasks = Array.isArray(task.tasks) ? task.tasks : [];
    if (!job.id) return '<div class="es-subsection es-job-task"><div class="es-section-label">' + escape(t('Profesn\u00ed \u00fakol', 'Job task')) + '</div><p class="es-muted">' + escape(t('Nejd\u0159\u00edv si vyber profesi ve h\u0159e.', 'Choose a job in-game first.')) + '</p></div>';
    if (!tasks.length) return '<div class="es-subsection es-job-task"><div class="es-section-label">' + escape(t('Profesn\u00ed \u00fakol', 'Job task')) + '</div><p class="es-muted">' + escape(t('Profesn\u00ed \u00fakol se zobraz\u00ed po dal\u0161\u00ed synchronizaci serveru.', 'The job task will appear after the next server sync.')) + '</p></div>';
    const chapter = number(task.chapter);
    const reward = task.reward_ready ? '<span class="es-task-ready">' + escape(t('Odm\u011bna p\u0159ipravena', 'Reward ready')) + '</span>' : '';
    return '<div class="es-subsection es-job-task"><div class="es-section-label">' + escape(t('Profesn\u00ed \u00fakol', 'Job task')) + '<span>' + escape(t('Kapitola ', 'Chapter ')) + chapter + ' \u00b7 ' + escape(strip(job.display || job.id)) + '</span></div><div class="es-job-task-list">' + tasks.map(item => '<div class="es-job-task-row"><div><strong>' + escape(strip(item.name || item.id)) + '</strong><span>' + (item.unlocked === false ? escape(t('Uzam\u010deno', 'Locked')) : item.complete ? escape(t('Dokon\u010deno', 'Complete')) : escape(t('Prob\u00edh\u00e1', 'In progress'))) + '</span></div><strong>' + number(item.progress) + ' / ' + number(item.target) + '</strong></div><div class="es-progress es-job-task-progress" role="progressbar" aria-label="' + escape(strip(item.name || item.id)) + '" aria-valuemin="0" aria-valuemax="' + number(item.target) + '" aria-valuenow="' + number(item.progress) + '"><span style="--es-progress-scale:' + (item.target ? Math.min(1, Number(item.progress) / Number(item.target)) : 0) + '"></span></div>').join('') + '</div>' + reward + '</div>';
  }
  function overview(snapshot) {
    const level = snapshot.level || {};
    const progress = levelProgress(level);
    const debt = Number(snapshot.debt?.coins || 0) + Number(snapshot.debt?.tokens || 0);
    const levelPanel = '<div class="es-level"><span class="es-level-number">' + number(progress.current) + '</span><div class="es-level-progress"><div class="es-level-head"><strong>' + t('Level ', 'Level ') + number(progress.current) + '</strong><span>' + (progress.current >= 100 ? t('Maxim\u00e1ln\u00ed level', 'Maximum level') : t('Dal\u0161\u00ed level: ', 'Next level: ') + number(progress.current + 1)) + '</span></div><div class="es-progress-labels"><span>' + number(progress.active) + ' / ' + number(progress.span) + ' XP ' + t('aktivn\u00ed postup', 'active progress') + '</span><span>' + progress.percent + '%</span></div><div class="es-progress" role="progressbar" aria-label="' + escape(t('Postup k dal\u0161\u00edmu levelu', 'Progress to next level')) + '" aria-valuemin="0" aria-valuemax="' + progress.span + '" aria-valuenow="' + progress.active + '"><span style="--es-progress-scale:' + (progress.percent / 100) + '"></span></div><div class="es-level-meta"><span>' + t('Celkem XP: ', 'Total XP: ') + number(progress.xp) + '</span><span>' + (progress.current >= 100 ? t('Dokon\u010deno', 'Complete') : t('Zb\u00fdv\u00e1 ', 'Remaining ') + number(progress.remaining) + ' XP') + '</span></div></div></div>' + xpSources();
    const jobPanel = '<div class="es-detail"><span>' + t('Profese', 'Job') + '</span><strong>' + escape(strip(snapshot.job?.display || snapshot.job?.id || t('Nevybran\u00e1', 'Not selected'))) + '</strong></div><div class="es-detail"><span>' + t('\u00darove\u0148 profese', 'Job level') + '</span><strong>' + number(snapshot.job?.level) + '</strong></div><div class="es-detail"><span>' + t('Denn\u00ed kalend\u00e1\u0159', 'Daily calendar') + '</span><strong>' + number(snapshot.daily?.day) + ' / 30</strong></div>' + currentTasks(snapshot) + jobTask(snapshot) + '<p>' + escape(t('Herní odměny vyzvedni ve hře. Webová denní odměna je samostatná; prohlížení webu nepřidává aktivní čas.', 'Claim gameplay rewards in-game. The daily website reward is separate; browsing does not add active time.')) + '</p>';
    return '<div class="es-grid">' + metricCard('Coins', snapshot.coins, t('Dostupn\u00fd z\u016fstatek', 'Available balance'), 'coins') + metricCard('Tokens', snapshot.tokens, t('\u010cekaj\u00edc\u00ed', 'Pending') + ': ' + number(snapshot.pending_tokens), 'tokens') + metricCard(t('Aktivn\u00ed minuty', 'Active minutes'), snapshot.active_minutes, t('Po\u010d\u00edt\u00e1 se pouze hra na serveru', 'Only server gameplay counts')) + '</div>' + panel(t('Tvoje \u00farove\u0148', 'Your level'), levelPanel) + panel(t('Profese a odm\u011bny', 'Job and rewards'), jobPanel) + (debt ? panel(t('Dluh po vr\u00e1cen\u00ed platby', 'Refund debt'), '<p>' + number(snapshot.debt.coins) + ' coins \u00b7 ' + number(snapshot.debt.tokens) + ' tokens</p><p>' + escape(t('Utr\u00e1cen\u00ed a p\u0159evody jsou pozastaven\u00e9, dokud dluh nesplat\u00ed\u0161. Dal\u0161\u00ed p\u0159\u00edjmy nejd\u0159\u00edv spl\u00e1cej\u00ed dluh p\u0159\u00edslu\u0161n\u00e9 m\u011bny.', 'Spending and transfers are paused until the debt is settled. Future income first pays down debt in the same currency.')) + '</p>') : '');
  }
  function statistics(snapshot) {
    const stats = snapshot.statistics || {};
    return panel(t('Tvoje statistiky', 'Your statistics'), table([t('Statistika', 'Statistic'), t('Celkem', 'All time'), t('Tento týden', 'This week')], Object.keys(statNames).map(key => row([escape(t(...statNames[key])), number(stats.all_time?.[key]), number(stats.weekly?.[key])])))) +
      panel(t('Žebříček hráčů, kteří souhlasili se zveřejněním', 'Opt-in player rankings'), `<div class="es-controls"><label for="ranking-metric">${t('Porovnat', 'Compare')}</label><select id="ranking-metric">${['playtime', 'blocks_mined', 'tasks_completed', 'duel_wins'].map(key => `<option value="${key}" ${key === metric ? 'selected' : ''}>${escape(t(...statNames[key]))}</option>`).join('')}</select></div>${rankings.length ? table(['#', t('Hráč', 'Player'), t('Hodnota', 'Value')], rankings.map((entry, i) => row([number(i + 1), escape(entry.name), number(entry.value)]))) : `<p>${t('Zatím žádní hráči.', 'No players yet.')}</p>`}<p>${escape(t('Zůstatky ani nákupy se nezveřejňují. Účast změníš v Nastavení.', 'Balances and purchases remain private. Change participation in Settings.'))}</p>`);
  }
  function progress(snapshot) {
    const achievements = snapshot.progress?.achievements || [];
    const jobs = snapshot.progress?.chapters || [];
    return panel(t('Denní a týdenní úkoly', 'Daily and weekly tasks'), currentTasks(snapshot) + '<p class="es-muted">' + escape(t('Postup a vyplácení odměn spravuje hra. Stejné úkoly otevřeš přes /tasks daily a /tasks weekly.', 'Progress and reward delivery are managed in-game. Use /tasks daily and /tasks weekly for the same tasks.')) + '</p>') +
      panel(t('Profese a achievementy', 'Jobs and achievements'), `<p>${escape(t('Vyzvednuté kapitoly aktuální profese', 'Claimed chapters in your current job'))}: ${jobs.map(number).join(', ') || '—'}</p><p>${escape(t('Dokončené achievementy', 'Completed achievements'))}: ${achievements.map(a => escape(strip(a.name || a))).join(', ') || '—'}</p>`) +
      panel(t('Denní kalendář', 'Daily calendar'), `<p>${t('Den', 'Day')} ${number(snapshot.daily?.day)} / 30 · Revive: ${number(snapshot.daily?.revives)} · ${t('Poslední odměna', 'Last claim')}: ${escape(snapshot.daily?.last_day || '—')}</p><div class="es-calendar">${Array.from({ length: 30 }, (_, i) => `<span class="${i < Number(snapshot.daily?.day || 0) ? 'earned' : ''}">${i + 1}</span>`).join('')}</div><p>${t('Odměny a obnovu série spravuj ve hře přes /daily. Reset je o půlnoci Europe/Prague.', 'Manage rewards and streak recovery in-game with /daily. Reset is at midnight Europe/Prague.')}</p>`) +
      panel(t('Tokeny za aktivní hru', 'Active-play tokens'), `<p>${snapshot.eligible ? t('Převody tokenů jsou odemčené.', 'Token transfers are unlocked.') : t('Převody vyžadují stáří účtu 48 hodin a 300 aktivních minut.', 'Transfers require an account age of 48 hours and 300 active minutes.')}</p><p>${t('Placené tokeny můžeš utrácet ihned. Omezení převodů zůstává stejné.', 'Paid tokens can be spent immediately. Transfer eligibility remains unchanged.')}</p>`);
  }
  function levelProgress(level) {
    const current = Math.max(1, Math.min(100, Number(level && level.level) || 1));
    const xp = Math.max(0, Number(level && level.xp) || 0);
    let currentStart = 0;
    for (let value = 1; value < current; value += 1) currentStart += Math.round(100 + 2.3 * Math.pow(value, 1.5));
    const nextTarget = current < 100 ? currentStart + Math.round(100 + 2.3 * Math.pow(current, 1.5)) : currentStart;
    const span = Math.max(1, nextTarget - currentStart);
    const active = current >= 100 ? 0 : Math.max(0, Math.min(span, xp - currentStart));
    return { current, xp, currentStart, nextTarget, span, active, remaining: Math.max(0, nextTarget - xp), percent: current >= 100 ? 100 : Math.round((active / span) * 100) };
  }
  function combinedPreview(cosmetics) {
    const selected = type => (cosmetics[type] || []).find(entry => entry.selected);
    const value = entry => entry && (entry.value ?? entry.display) || '';
    const prefix = strip(value(selected('prefix')));
    const title = ''; // Cosmetic titles were retired; rank identity is separate.
    const colour = value(selected('color'));
    return chatPreview(colour + (prefix ? prefix + ' ' : '') + (title ? title + ' ' : '') + account.link.name + ': ' + t('Ukázka zprávy', 'Example message'));
  }
  function appearance(snapshot) {
    const cosmetics = snapshot.cosmetics || {};
    const definitions = [['prefix', t('Prefix', 'Prefix')], ['color', t('Barva chatu', 'Chat colour')], ['aura', t('Aura', 'Aura')], ['hat', t('Klobouk', 'Hat')]];
    const controls = definitions.map(([type, label]) => {
      const entries = cosmetics[type] || [];
      return '<div class="es-cosmetic-control"><label for="cosmetic-' + type + '">' + escape(label) + '</label><select id="cosmetic-' + type + '" name="' + type + '"><option value="">' + t('Vypnuto', 'Off') + '</option>' + entries.filter(entry => entry.owned).map(entry => '<option value="' + escape(entry.id) + '"' + (entry.selected ? ' selected' : '') + '>' + escape(strip(entry.display || entry.id)) + '</option>').join('') + '</select></div>';
    }).join('');
    const locked = definitions.some(([type]) => (cosmetics[type] || []).some(entry => !entry.owned));
    return rankPanel(snapshot) + panel(t('Vzhled ve hře', 'In-game appearance'), '<p>' + escape(t('Vyber vzhled a zkontroluj náhled chatu. Rankové položky vyžadují aktivní rank.', 'Choose your appearance and review the chat preview. Rank cosmetics require an active rank.')) + '</p><form id="appearance-form" class="es-form cosmetic-combined-form"><div class="es-cosmetic-controls">' + controls + '</div><div class="es-combined-preview-label">' + t('Společný náhled chatu', 'Combined chat preview') + '</div><div id="combined-appearance-preview" class="es-preview es-combined-preview" aria-live="polite">' + combinedPreview(cosmetics) + '</div><button type="submit">' + t('Použít vzhled', 'Apply appearance') + '</button></form>' + (locked ? '<p class="es-muted">' + t('Další vzhledy odemkneš ve hře.', 'Unlock more appearances in-game.') + '</p>' : '')) +
      panel(t('Synchronizace změn', 'Change synchronization'), '<p>' + t('Změny se použijí po potvrzení serverem. Když je server vypnutý, zůstanou čekat.', 'Changes apply after server confirmation. When the server is stopped, they remain queued.') + '</p>' + (account.cosmetic_operations || []).map(op => '<p class="es-muted">' + escape(op.id.slice(0, 8)) + ': ' + escape(op.state === 'pending' ? t('Čeká na server', 'Waiting for server') : op.state === 'failed' ? t('Změnu se nepodařilo použít', 'Change could not be applied') : t('Použito', 'Applied')) + '</p>').join(''));
  }
  function productLabel(product) {
    if (product.currency === 'rank' || product.currency_type === 'rank') return escape(({vip:'VIP',vipplus:'VIP+',mvp:'MVP'})[product.rank_id] || 'Rank') + ' · ' + t('7 dní', '7 days');
    return number(product.amount ?? product.currency_amount) + ' ' + escape(product.currency || product.currency_type);
  }
  function rankPanel(snapshot) {
    const rank = snapshot.rank || {}; const names = {vip:'VIP',vipplus:'VIP+',mvp:'MVP'};
    const stale = !!names[rank.id] && (!Number.isFinite(Number(rank.expires_at)) || Number(rank.expires_at) <= Date.now());
    const frame = stale ? 0 : Math.max(0, Math.min(3, Number(rank.frame) || 0));
    return panel(t('Tvůj rank', 'Your rank'), '<div class="es-rank-profile es-rank-frame-' + frame + '"><strong>' + escape(stale ? t('Čeká na synchronizaci', 'Waiting for synchronization') : names[rank.id] || t('Hráč', 'Player')) + '</strong><p>' + (stale ? t('Poslední uložená platnost skončila. Obnov data ze serveru pro aktuální rank.', 'The last saved expiry has passed. Refresh server data for the current rank.') : names[rank.id] ? t('Platí do: ', 'Expires: ') + escape(date(Number(rank.expires_at) / 1000)) : t('Nemáš aktivní podporovatelský rank.', 'No supporter rank is currently active.')) + '</p>' + ['vip','vipplus','mvp'].filter(id => id !== rank.id && Number(rank.remaining_ms?.[id]) > 0).map(id => '<p>' + names[id] + ': ' + number(Math.ceil(Number(rank.remaining_ms[id])/3600000)) + ' h · ' + t('pozastaveno', 'paused') + '</p>').join('') + '<p>' + t('Rankové nastavení vzhledu upravíš ve hře v /cosmetics.', 'Change rank appearance in-game with /cosmetics.') + '</p></div>', 'es-rank-section');
  }
  const rankIds = ['vip', 'vipplus', 'mvp'];
  const rankNames = { vip: 'VIP', vipplus: 'VIP+', mvp: 'MVP' };
  const rankSymbols = {
    vip: '<path d="m3 7 4 3 5-7 5 7 4-3-2 13H5L3 7Zm2 9h14"/>',
    vipplus: '<path d="M12 2 21 6v6c0 5-9 10-9 10S3 17 3 12V6l9-4Z"/><path d="m8 12 3 3 5-6"/>',
    mvp: '<path d="m6 3-4 6 10 13L22 9l-4-6H6Zm-4 6h20M6 3l6 19 6-19M6 3l6 6 6-6"/>'
  };
  const rankSymbol = id => '<svg class="es-rank-symbol" viewBox="0 0 24 24" aria-hidden="true">' + (rankSymbols[id] || '') + '</svg>';
  function rankBenefits() {
    return [
      [t('Aury', 'Auras'), ['Zlatá svatozář', 'Zlatá svatozář · Duhový vír', 'Zlatá svatozář · Duhový vír · Pantheon aura'].map((v,i) => t(v, ['Golden halo','Golden halo · Rainbow vortex','Golden halo · Rainbow vortex · Pantheon aura'][i]))],
      [t('Klobouky', 'Hats'), [t('Koruna','Crown'), t('Koruna · Dračí hlava','Crown · Dragon head'), t('Koruna · Dračí hlava · Zlatý blok','Crown · Dragon head · Gold block')]],
      [t('Společníci', 'Pets'), [t('Včela','Bee'), t('Včela · Slime','Bee · Slime'), t('Včela · Slime · Drak','Bee · Slime · Dragon')]],
      [t('Emoty', 'Emotes'), [t('Mávání · Srdíčka','Wave · Hearts'), t('Mávání · Srdíčka · Hudba · Oslava','Wave · Hearts · Music · Celebration'), t('Mávání · Srdíčka · Hudba · Oslava · Koruna · Konfety','Wave · Hearts · Music · Celebration · Crown · Confetti')]],
      [t('Příchodové efekty','Arrival effects'), [t('Portál','Portal'), t('Portál · Ohňostroje','Portal · Fireworks'), t('Portál · Ohňostroje · Zlaté ohňostroje','Portal · Fireworks · Golden fireworks')]],
      [t('Sestavy / barvy / rámečky','Presets / colours / frames'), ['3 / 3 / 1','6 / 6 / 2','10 / 12 / 3']],
      [t('Crafting v lobby','Lobby crafting'), [t('Ano','Yes'),t('Ano','Yes'),t('Ano','Yes')]],
      [t('Vlastní ender chest v lobby','Own ender chest in lobby'), ['—',t('Ano','Yes'),t('Ano','Yes')]],
      [t('Vlastní jméno společníka','Custom pet name'), ['—',t('Ano','Yes'),t('Ano','Yes')]],
      [t('Glow v lobby / dvoubarevný odznak','Lobby glow / two-colour badge'), ['—','—',t('Ano','Yes')]],
      [t('Společný booster','Shared booster'), ['30 min','45 min','60 min']],
      [t('Postup práce pro všechny','Job progress for everyone'), ['+5 %','+10 %','+15 %']],
      [t('Denní coiny pro všechny','Daily coins for everyone'), ['+10 %','+20 %','+30 %']]
    ];
  }
  function rankRules() {
    return '<p class="es-rank-rules">' + t('Vyšší rank zahrnuje nižší výhody. Jednorázový nákup, bez předplatného. Sedm dní běží od potvrzení platby i offline; vyšší rank pozastaví čas nižšího. Booster smí spustit každý dárce jednou za 168 hodin, bez skládání, nejvýše 120 minut aktivací serveru denně. Bonus dostanou všichni, nikoli jen platící hráči.', 'Higher ranks include lower-tier perks. One-time payment, no subscription. Seven days run from payment confirmation including offline time; a higher rank pauses lower-tier time. Each donor can activate a booster once per 168 hours, without stacking, with a server-wide 120-minute daily activation limit. Everyone receives the bonus, not only paying players.') + '</p>';
  }
  function rankCard(pack) {
    const id = pack.rank_id;
    if (!rankIds.includes(id)) return '';
    return '<article class="es-rank-card es-tier-' + id + '"><button class="es-rank-details-trigger" type="button" data-rank="' + id + '" aria-haspopup="dialog" aria-label="' + escape(t('Zobrazit všechny výhody ', 'View all benefits of ') + rankNames[id]) + '"><span class="es-rank-crest">' + rankSymbol(id) + '</span><strong class="es-rank-name">' + rankNames[id] + '</strong><span class="es-rank-tagline">' + t('Tvůj vlastní styl. Podpora Pantheonu.', 'Your own style. Support Pantheon.') + '</span><span class="es-rank-cost">' + money(pack.price_minor) + '<small> / ' + t('7 dní','7 days') + '</small></span><span class="es-rank-card-summary">' + escape(t(...[['Zlatá aura, koruna a včelí společník','Golden aura, crown and bee companion'],['Duhový vír, dračí hlava a vlastní ender chest','Rainbow vortex, dragon head and own ender chest'],['Pantheon aura, dračí společník a glow v lobby','Pantheon aura, dragon companion and lobby glow']][rankIds.indexOf(id)])) + '</span><span class="es-rank-details-link">' + t('Prohlédnout všechny výhody','Explore all benefits') + ' <span aria-hidden="true">↗</span></span></button></article>';
  }
  function rankDialog() {
    return '<dialog id="rank-details-dialog" class="es-rank-dialog" aria-labelledby="rank-details-title"><button type="button" class="es-modal-close" id="close-rank-details" aria-label="' + t('Zavřít','Close') + '">×</button><div id="rank-details-content"></div></dialog>';
  }
  function rankDetail(id) {
    const index = rankIds.indexOf(id), pack = packages.find(p => p.currency === 'rank' && p.rank_id === id);
    if (index < 0 || !pack) return '';
    const canBuy = purchasesEnabled && account?.link && pack.checkoutable !== false;
    return '<header class="es-rank-detail-header">' + rankSymbol(id) + '<p class="es-eyebrow">PANTHEON / ' + t('PODPOROVATELSKÝ RANK','SUPPORTER RANK') + '</p><h2 id="rank-details-title">' + rankNames[id] + '</h2><p>' + money(pack.price_minor) + ' / ' + t('7 dní · bez předplatného','7 days · no subscription') + '</p></header><div class="es-rank-detail-body"><p class="es-rank-includes">' + t('Všechny výhody, včetně nižších ranků','All benefits, including lower tiers') + '</p><dl class="es-rank-benefits">' + rankBenefits().map(([label,values]) => '<div' + (values[index] === '—' ? ' class="is-unavailable"' : '') + '><dt>' + escape(label) + '</dt><dd>' + escape(values[index] === '—' ? t('Není součástí','Not included') : values[index]) + '</dd></div>').join('') + '</dl>' + rankRules() + '<div class="es-rank-detail-actions">' + (canBuy ? '<button type="button" class="es-primary" id="order-rank" data-price="' + escape(pack.id) + '">' + t('Objednat ', 'Order ') + rankNames[id] + ' · ' + money(pack.price_minor) + '</button>' : !account ? '<a class="es-button es-primary" href="/login?product=economysuite&amp;next=' + encodeURIComponent('/economysuite/' + route) + '">' + t('Přihlásit se pro nákup','Sign in to purchase') + '</a>' : !account.link ? '<a class="es-button es-primary" href="/economysuite/pair">' + t('Nejdřív propojit hráče','Pair your player first') + '</a>' : '<p>' + t('Prodej momentálně není dostupný.','Sales are currently unavailable.') + '</p>') + '<a href="/economysuite/rank">' + t('Porovnat ranky','Compare ranks') + '</a></div></div>';
  }
  function rankComparison() {
    const columns = rankIds.map(id => { const pack = packages.find(p => p.currency === 'rank' && p.rank_id === id); return '<th scope="col" class="es-tier-' + id + '">' + rankSymbol(id) + '<strong>' + rankNames[id] + '</strong><span>' + (pack ? money(pack.price_minor) + ' / ' + t('7 dní','7 days') : t('Nyní nedostupné','Currently unavailable')) + '</span></th>'; }).join('');
    const rows = rankBenefits().map(([label,values]) => '<tr><th scope="row">' + escape(label) + '</th>' + values.map((value,i) => '<td class="es-tier-' + rankIds[i] + '">' + escape(value) + '</td>').join('')).join('');
    return '<section class="es-panel es-rank-comparison"><h2>' + t('Každý rank má svůj styl','Every rank has its own style') + '</h2><p>' + t('Vyber si podle výhod. Každý vyšší rank obsahuje i vše z těch předchozích.','Choose by benefits. Each higher tier also includes everything from the tiers below.') + '</p><div class="es-rank-table-scroll" tabindex="0" role="region" aria-label="' + t('Porovnání všech výhod ranků','Compare all rank benefits') + '"><table class="es-rank-table"><caption class="es-sr-only">' + t('Výhody VIP, VIP+ a MVP','VIP, VIP+ and MVP benefits') + '</caption><thead><tr><th scope="col">' + t('Výhoda','Benefit') + '</th>' + columns + '</tr></thead><tbody>' + rows + '</tbody></table></div>' + rankRules() + '</section>';
  }
  function rankPage() {
    return '<div class="es-rank-intro"><p class="es-eyebrow">' + t('PODPOŘ PANTHEON · VYBER SI SVŮJ STYL','SUPPORT PANTHEON · CHOOSE YOUR STYLE') + '</p><h2>' + t('Tři ranky. Jeden Pantheon.','Three ranks. One Pantheon.') + '</h2><p>' + t('Kosmetika pro tebe, společné boostery pro všechny. Bez automatického obnovování.','Cosmetics for you, shared boosters for everyone. No automatic renewal.') + '</p></div><div class="es-rank-cards">' + packages.filter(p => p.currency === 'rank').map(rankCard).join('') + '</div>' + rankComparison() + rankDialog();
  }
  function dailyRewardCard() {
    const reward = account?.daily_reward;
    let content;
    if (!account) content = '<a class="es-button" href="/login?product=economysuite">' + t('Přihlásit se', 'Sign in') + '</a>';
    else if (!account.link) content = '<a class="es-button" href="/economysuite/pair">' + t('Propojit Minecraft účet', 'Pair Minecraft account') + '</a>';
    else if (!reward) content = '<p class="es-muted">' + t('Stav odměny zatím není dostupný.', 'Reward status is not available yet.') + '</p>';
    else if (reward.available) content = '<button id="claim-web-daily" class="es-primary" type="button"' + (dailyClaimPending ? ' disabled' : '') + '>' + t('Vyzvednout 1–5 tokenů zdarma', 'Claim 1–5 free tokens') + '</button>';
    else {
      const state = reward.status === 'delivered' ? t('Připsáno', 'Credited') : reward.status === 'failed' ? t('Doručení musí zkontrolovat správce. Dnes již znovu nelosuj.', 'An administrator needs to check delivery. Today’s reward cannot be rerolled.') : t('Odměna čeká na server', 'Reward is waiting for the server');
      content = '<p role="status"><strong>' + number(reward.amount) + ' ' + t('tokenů', 'tokens') + '</strong> · ' + escape(state) + '</p>';
    }
    const reset = reward?.next_reset_at ? '<p class="es-muted">' + t('Další odměna', 'Next reward') + ': ' + escape(new Date(reward.next_reset_at * 1000).toLocaleString(lang === 'en' ? 'en-GB' : 'cs-CZ', { timeZone: 'Europe/Prague' })) + ' (Europe/Prague)</p>' : '';
    return '<div id="web-daily-reward">' + panel(t('Denní webová odměna', 'Daily website reward'), '<p>' + t('Jednou denně náhodných <strong>1–5 tokenů</strong> zdarma. Nákup ani rank nejsou potřeba. Herní /daily zůstává samostatné.', 'Claim <strong>1–5 random tokens</strong> free each day. No purchase or rank required. In-game /daily stays separate.') + '</p>' + content + reset + '<p class="es-muted">' + t('Při offline serveru se odměna bezpečně doručí později. Platí běžné podmínky odemčení tokenů; do té doby jsou čekající.', 'If the server is offline, delivery safely waits. Normal token eligibility rules apply; tokens remain pending until unlocked.') + '</p>') + '</div>';
  }
  function refreshDailyReward() {
    const host = $('#web-daily-reward');
    if (!host) return;
    host.outerHTML = dailyRewardCard();
    bindDailyReward();

  }
  function bindDailyReward() {
    $('#claim-web-daily')?.addEventListener('click', event => {
      const button = event.currentTarget;
      if (dailyClaimPending || button.disabled) return;
      dailyClaimPending = true;
      action(button, async () => {
        try {
          const result = await api('/api/economysuite/daily/claim', {});
          account.daily_reward = result.daily_reward;
          status(t('Denní odměna je uložená a čeká na doručení serverem.', 'Your daily reward is saved and waiting for server delivery.'), false, 'success');
        } finally { dailyClaimPending = false; refreshDailyReward(); }
      });
    });
  }
  function storePurchaseDialog() {
    return '<div id="purchase-dialog" class="es-modal" hidden role="dialog" aria-modal="true" aria-labelledby="purchase-dialog-title"><div class="es-modal-backdrop" data-close-purchase></div><section class="es-modal-card" role="document"><button id="close-purchase-dialog" class="es-modal-close" type="button" aria-label="' + t('Zavřít', 'Close') + '">×</button><p class="es-eyebrow">' + t('PŘED PLATBOU', 'BEFORE PAYMENT') + '</p><h2 id="purchase-dialog-title">' + t('Zkontroluj objednávku', 'Review your order') + '</h2><div id="purchase-dialog-summary" class="es-order-summary"></div><form id="purchase-consent-form" class="es-purchase-consent"><label><input id="accept-purchase-terms" type="checkbox" required>' + t('Souhlasím s <a href="https://tomaspisar.cz/legal/economysuite-purchases/" target="_blank" rel="noopener">podmínkami nákupu EconomySuite</a>.', 'I accept the <a href="https://tomaspisar.cz/legal/economysuite-purchases/" target="_blank" rel="noopener">EconomySuite purchase terms</a>.') + '</label><label><input id="request-immediate-delivery" type="checkbox" required>' + t('Výslovně žádám o okamžité digitální dodání a beru na vědomí příslušný dopad na právo na odstoupení.', 'I expressly request immediate digital delivery and acknowledge the applicable effect on the withdrawal right.') + '</label><p class="es-muted">' + t('Dodání proběhne po potvrzení platby. Při offline serveru zůstane nákup ve frontě. <a href="https://tomaspisar.cz/legal/refunds/" target="_blank" rel="noopener">Vrácení a odstoupení</a>.', 'Delivery starts after payment confirmation. If the server is offline, the purchase remains queued. <a href="https://tomaspisar.cz/legal/refunds/" target="_blank" rel="noopener">Refunds and withdrawal</a>.') + '</p><div class="es-modal-actions"><button id="cancel-purchase" type="button">' + t('Zpět', 'Back') + '</button><button id="confirm-purchase" class="es-primary" type="submit">' + t('Potvrdit a pokračovat k platbě', 'Confirm and continue to checkout') + '</button></div></form></section></div>';
  }
  function store() {
    const support = '<div class="es-store-note"><strong>' + t('Podpora vývoje', 'Support the developer') + '</strong><span>' + t('Nákup podporuje vývoj a provoz EconomySuite týmu Novaryn Solutions.', 'Your purchase supports EconomySuite development and operation by Novaryn Solutions.') + '</span></div>';
    const modal = storePurchaseDialog();
    return support + (packages.length ? '<div class="es-grid es-store-grid">' + packages.filter(pack => pack.currency !== 'rank').map(pack => panel(pack.name, '<div class="es-pack-amount">' + currencyIcon(pack.currency) + '<span>' + productLabel(pack) + '</span></div><p>' + escape(pack.description) + '</p><span class="es-pack-price">' + money(pack.price_minor) + ' <small>CZK</small></span><p class="es-muted">' + t('Digitální obsah · bez dopravy · dodání po potvrzení platby', 'Digital content · no shipping · delivery after payment confirmation') + '</p>' + (pack.checkoutable === false ? '<p class="es-muted es-pack-unavailable">' + t('Stripe vyžaduje minimální platbu 15 Kč. Zvol vyšší balíček.', 'Stripe requires a minimum 15 CZK payment. Choose a larger package.') + '</p>' : '') + '<button class="es-primary buy" type="button" data-price="' + escape(pack.id) + '" data-amount="' + pack.price_minor + '"' + (!purchasesEnabled || !account?.link || pack.checkoutable === false ? ' disabled' : '') + ' aria-haspopup="dialog">' + icon('store') + (pack.checkoutable === false ? t('Nedostupné přes Stripe', 'Unavailable through Stripe') : t('Objednat', 'Order')) + '</button>', 'es-pack')).join('') + '</div>' : panel(t('Obchod se připravuje.', 'The store is being prepared.'), '<p>' + escape(t('Balíčky a ceny zde budou zveřejněné před otevřením prodeje.', 'Packages and prices will be published here before sales open.')) + '</p>', 'es-empty')) + modal;
  }
  function purchases() {
    const labels = { checkout: ['Čeká na platbu', 'Awaiting payment'], cancelled: ['Zrušeno', 'Cancelled'], paid: ['Zaplaceno', 'Paid'], refunded: ['Vráceno', 'Refunded'], partially_refunded: ['Částečně vráceno', 'Partially refunded'], disputed: ['Spor o platbu', 'Payment dispute'] };
    const filters = [['paid', t('Zaplacené', 'Paid')], ['all', t('Všechny', 'All')], ['checkout', t('Čekající platby', 'Awaiting payment')], ['cancelled', t('Zrušené', 'Cancelled')], ['refunded', t('Vrácené', 'Refunded')], ['partially_refunded', t('Částečně vrácené', 'Partially refunded')], ['disputed', t('Sporné', 'Disputed')]];
    const filtered = purchaseFilter === 'all' ? orders : orders.filter(order => order.state === purchaseFilter);
    const thanks = successfulOrder ? thankYou(orders.find(order => order.id === successfulOrder)) : '';
    const rows = filtered.map(order => {
      const receipt = /^https:\/\/(pay|invoice|dashboard)\.stripe\.com\//.test(order.receipt_url || '') ? '<a href="' + escape(order.receipt_url) + '" rel="noopener" target="_blank">' + t('Otevřít', 'Open') + '</a>' : '—';
      const delivery = order.revision > 0 ? order.delivered_revision >= order.revision ? t('Potvrzeno serverem', 'Confirmed by server') : t('Čeká na server', 'Waiting for server') : '';
      const confirmation = order.order_confirmation_sent_at ? t('Potvrzení e-mailem', 'Email confirmation') : t('Potvrzení čeká', 'Confirmation pending');
      return row([escape(date(order.created_at)), '<span class="es-order-item">' + currencyIcon(order.currency_type) + '<span>' + productLabel(order) + '<br><span class="es-muted">' + escape(order.player_name) + '</span></span></span>', money(order.price_minor), escape(t(...(labels[order.state] || [order.state, order.state]))) + '<br><span class="es-muted">' + escape(delivery) + '</span>', receipt + '<br><span class="es-muted">' + escape(confirmation) + '</span>']);
    });
    const emptyMessage = purchaseFilter === 'paid' ? t('Zatím nemáš žádné zaplacené nákupy.', 'You have no paid purchases yet.') : t('Tento filtr zatím nic neobsahuje.', 'This filter has no purchases yet.');
    return thanks + panel(t('Historie nákupů', 'Purchase history'), '<div class="es-controls es-purchase-filters"><label for="purchase-filter">' + t('Zobrazit', 'Show') + '</label><select id="purchase-filter">' + filters.map(([value, label]) => '<option value="' + value + '"' + (value === purchaseFilter ? ' selected' : '') + '>' + escape(label) + '</option>').join('') + '</select><span class="es-muted">' + number(filtered.length) + ' ' + t('záznamů', 'records') + '</span></div>' + (rows.length ? table([t('Datum', 'Date'), t('Balíček', 'Package'), t('Cena', 'Price'), t('Stav', 'Status'), t('Doklad', 'Receipt')], rows) : '<p class="es-empty-filter">' + emptyMessage + '</p>'));
  }
  function thankYou(order) {
    const paid = order && order.revision > 0, delivered = paid && order.delivered_revision >= order.revision;
    const state = delivered ? 'delivered' : paid ? 'delivering' : 'confirming';
    const heading = delivered ? t('Děkujeme! Nákup je ve hře.', 'Thank you! Your purchase is in-game.') : paid ? t('Děkujeme za nákup.', 'Thank you for your purchase.') : t('Děkujeme. Ověřujeme platbu.', 'Thank you. We are confirming your payment.');
    const detail = delivered ? t('Server doručení potvrdil. Zůstatek uvidíš přes /money nebo /tokens.', 'The server confirmed delivery. Check your balance with /money or /tokens.') : paid ? t('Platba je potvrzená a server balíček doručuje. Obvykle to trvá do pěti sekund.', 'Payment is confirmed and the server is delivering your package. This usually takes up to five seconds.') : t('Stripe nás právě vrací k objednávce. Potvrzení může trvat až 30 sekund; stránku můžeš bezpečně opustit.', 'Stripe is returning you to the order. Confirmation can take up to 30 seconds; you may safely leave this page.');
    const item = order ? `<div class="es-thanks-item">${currencyIcon(order.currency_type)}<strong>${productLabel(order)}</strong><span>${money(order.price_minor)}</span></div>` : '';
    return `<section class="es-thanks" data-state="${state}"><div class="es-thanks-check" aria-hidden="true">${delivered ? '✓' : '···'}</div><div><p class="es-eyebrow">STRIPE / PANTHEON</p><h2>${heading}</h2><p>${detail}</p>${item}<ol><li>${t('Připoj se na Pantheon.', 'Join Pantheon.')}</li><li>${t('Otevři chat a použij /money nebo /tokens.', 'Open chat and use /money or /tokens.')}</li><li>${t('Když je server offline, nákup zůstane bezpečně čekat.', 'If the server is offline, the purchase remains safely queued.')}</li></ol></div></section>`;
  }
  function settings() {
    return panel(t('Propojený hráč', 'Paired player'), account.link ? `<p><strong>${escape(account.link.name)}</strong><br><span class="es-muted">${escape(account.link.uuid)}</span></p><form id="unlink-form" class="es-form"><label for="unlink-password">${t('Potvrď odpojení heslem k webovému účtu', 'Confirm unlinking with your website password')}</label><input id="unlink-password" type="password" autocomplete="current-password" required><button type="submit" class="es-danger">${t('Odpojit hráče', 'Unlink player')}</button></form>` : empty()) +
      (account.link ? panel(t('Soukromí', 'Privacy'), `<form id="privacy-form" class="es-form"><label class="es-inline"><input id="leaderboard-opt-in" type="checkbox" ${account.link.leaderboard ? 'checked' : ''}>${t('Zveřejnit Minecraft jméno a vybrané statistiky v žebříčku', 'Publish my Minecraft name and selected statistics in rankings')}</label><p>${t('Zobrazení v žebříčku je ve výchozím nastavení zapnuté. Vypnout ho můžeš zde. Zůstatky, e-mail a nákupy zůstávají soukromé.', 'Leaderboard visibility is on by default. You can turn it off here. Balances, email, and purchases remain private.')}</p><button type="submit">${t('Uložit', 'Save')}</button></form>`) : '') +
      panel(t('Heslo k účtu', 'Account password'), `<form id="password-form" class="es-form"><label for="current-password">${t('Současné heslo', 'Current password')}</label><input id="current-password" type="password" autocomplete="current-password" required><label for="new-password">${t('Nové heslo', 'New password')}</label><input id="new-password" type="password" autocomplete="new-password" minlength="12" required><label for="confirm-password">${t('Potvrdit nové heslo', 'Confirm new password')}</label><input id="confirm-password" type="password" autocomplete="new-password" minlength="12" required><p>${t('Alespoň 12 znaků, písmeno, číslo a symbol.', 'At least 12 characters, a letter, a number, and a symbol.')}</p><button type="submit">${t('Změnit heslo', 'Change password')}</button></form>`) + panel(t('Moje data', 'My data'), `<p>${t('Stáhni si kopii údajů účtu a požádej o výmaz po ověření heslem. Platební, účetní a bezpečnostní údaje mohou zůstat uchované podle práva.', 'Download a copy of your account data and request deletion after password verification. Payment, accounting, and security records may need to remain under law.')}</p><div class="es-button-row"><button id="export-data" type="button">${t('Exportovat data', 'Export data')}</button></div><form id="deletion-form" class="es-form"><label for="deletion-password">${t('Heslo pro žádost o výmaz', 'Password for deletion request')}</label><input id="deletion-password" type="password" autocomplete="current-password" required><button type="submit" class="es-danger">${t('Požádat o výmaz účtu', 'Request account deletion')}</button></form>`) + panel('Podpora / Support', `<p>${escape(account.email)}</p><a href="https://tomaspisar.cz/contact/?product=economysuite">${t('Nahlásit problém', 'Report a problem')}</a>`);
  }
  let pairing = null, pairingToken = '', pairConfirmation = '';
  try {
    const fragment = new URLSearchParams(location.hash.slice(1)).get('pair');
    if (fragment && /^[A-Za-z0-9_-]{20,256}$/.test(fragment)) { sessionStorage.setItem('es-pair', JSON.stringify({ token: fragment, expires: Date.now() + 300000 })); history.replaceState({}, '', location.pathname + location.search); }
    const pending = JSON.parse(sessionStorage.getItem('es-pair') || 'null');
    if (pending?.expires > Date.now()) pairingToken = pending.token; else sessionStorage.removeItem('es-pair');
    pairConfirmation = sessionStorage.getItem('es-pair-confirmation') || '';
  } catch { /* pairing can be restarted in-game */ }
  function onboardingGuide(active) {
    const steps = [
      [t('Otevři portál a přihlas se', 'Open the portal and sign in'), t('Ve hře zadej /web link, otevři odkaz a přihlas se nebo si vytvoř účet.', 'Run /web link in game, open the link and sign in or create an account.')],
      [t('Potvrď svého hráče', 'Confirm your player'), t('Zkontroluj Minecraft jméno a potvrď, že patří tobě.', 'Check the Minecraft name and confirm that it belongs to you.')],
      [t('Dokonči propojení ve hře', 'Finish in Minecraft'), t('Zkopíruj příkaz z této stránky a odešli ho v chatu hry.', 'Copy the command from this page and send it in game chat.')]
    ];
    return '<ol class="es-onboarding-steps" aria-label="' + escape(t('Kroky propojení', 'Pairing steps')) + '">' + steps.map((step, index) => { const number = index + 1; const current = number === active; const state = number < active ? ' is-done' : current ? ' is-active' : ''; return '<li class="es-onboarding-step' + state + '"' + (current ? ' aria-current="step"' : '') + '><span class="es-onboarding-number" aria-hidden="true">' + (number < active ? '&#10003;' : number) + '</span><div>' + (current ? '<span class="es-next-label">' + t('Další krok', 'Next step') + '</span>' : '') + '<strong>' + escape(step[0]) + '</strong><span>' + escape(step[1]) + '</span></div></li>'; }).join('') + '</ol>';
  }
  function onboardingCard(title, content, cls = 'is-next') {
    return '<div class="es-onboarding-card ' + cls + '"><h3>' + escape(title) + '</h3>' + content + '</div>';
  }
  function pairingPage() {
    if (!account) return panel(t('Propojen\u00ed \u00fa\u010dtu krok za krokem', 'Pair your account step by step'), onboardingGuide(1) + onboardingCard(t('P\u0159ihlas se a pokra\u010duj', 'Sign in to continue'), '<p>' + escape(t('Po p\u0159ihl\u00e1\u0161en\u00ed se vr\u00e1t\u00ed\u0161 p\u0159\u00edmo na tento proces. Odkaz z Minecraftu z\u016fstane platn\u00fd p\u011bt minut.', 'After signing in, you will return to this process. The Minecraft link stays valid for five minutes.')) + '</p><a class="es-button es-primary" href="/login?product=economysuite&next=/economysuite/pair">' + t('P\u0159ihl\u00e1sit se nebo registrovat', 'Sign in or create account') + '</a>'));
    if (account.link) { sessionStorage.removeItem('es-pair-confirmation'); return panel(t('Propojen\u00ed je hotov\u00e9', 'Pairing is complete'), onboardingGuide(4) + onboardingCard(t('Minecraft \u00fa\u010det je propojen\u00fd', 'Your Minecraft account is paired'), '<p><strong>' + escape(account.link.name) + '</strong></p><p>' + escape(t('Te\u010f m\u016f\u017ee\u0161 otev\u0159\u00edt p\u0159ehled a zobrazit sv\u00e9 statistiky, levely a n\u00e1kupy.', 'You can now open the overview and view your statistics, levels, and purchases.')) + '</p><a class="es-button es-primary" href="/economysuite/overview">' + t('Otev\u0159\u00edt p\u0159ehled', 'Open overview') + '</a>', 'is-complete')); }
    if (pairConfirmation) return panel(t('Posledn\u00ed krok ve h\u0159e', 'Final step in Minecraft'), onboardingGuide(3) + onboardingCard(t('Vlo\u017e tento p\u0159\u00edkaz do chatu Minecraftu', 'Enter this command in Minecraft chat'), '<div class="es-pair-command"><code class="es-command" id="pair-command-value">' + escape(pairConfirmation) + '</code><button id="copy-pair-command" type="button">' + t('Kop\u00edrovat p\u0159\u00edkaz', 'Copy command') + '</button></div><p>' + escape(t('Vra\u0165 se do Minecraftu, vlo\u017e p\u0159\u00edkaz a ode\u0161li ho. Server ti potvrd\u00ed, \u017ee je \u00fa\u010det propojen\u00fd.', 'Return to Minecraft, paste the command, and send it. The server will confirm that your account is paired.')) + '</p><p class="es-muted">' + escape(t('K\u00f3d plat\u00ed p\u011bt minut. Kdy\u017e vypr\u0161\u00ed, spus\u0165 ve h\u0159e znovu /web link.', 'The code expires in five minutes. If it expires, run /web link again.')) + '</p>'));
    if (!pairing) return panel(t('Propojen\u00ed \u00fa\u010dtu krok za krokem', 'Pair your account step by step'), onboardingGuide(1) + onboardingCard(t('Za\u010dni ve h\u0159e', 'Start in Minecraft'), '<p>' + escape(t('P\u0159ipoj se na Pantheon, otev\u0159i chat a zadej p\u0159esn\u011b tento p\u0159\u00edkaz:', 'Join Pantheon, open chat, and enter exactly this command:')) + '</p><code class="es-command">/web link</code><p class="es-muted">' + escape(t('Server ti po\u0161le klikac\u00ed odkaz. Klikni na n\u011bj a pokra\u010duj podle t\u00e9to str\u00e1nky.', 'The server will send you a clickable link. Click it and follow this page.')) + '</p>'));
    return panel(t('Zkontroluj hr\u00e1\u010de', 'Check your player'), onboardingGuide(2) + onboardingCard(t('Je to tv\u016fj Minecraft \u00fa\u010det?', 'Is this your Minecraft account?'), '<p class="es-pair-player"><strong>' + escape(pairing.name) + '</strong></p><p>' + escape(t('Potvr\u010f pouze sv\u00e9 vlastn\u00ed Minecraft jm\u00e9no. T\u00edmto krokem web z\u00edsk\u00e1 opr\u00e1vn\u011bn\u00ed dokon\u010dit propojen\u00ed.', 'Only confirm your own Minecraft name. This step authorizes the website to finish pairing.')) + '</p><button id="approve-pair" class="es-primary" type="button">' + t('Ano, potvrdit hr\u00e1\u010de', 'Yes, confirm this player') + '</button>'));
  }
  function renderConnection() {
    const refreshing = refreshBaseline !== null;
    const state = refreshing ? 'connecting' : account?.server_status || 'connecting';
    const labels = { connected: ['Server je připojený', 'Server connected'], connecting: ['Server se připojuje…', 'Server connecting…'], disconnected: ['Server je odpojený', 'Server disconnected'] };
    const connection = $('#connection');
    connection.dataset.state = state;
    connection.closest('.es-live-actions').dataset.state = state;
    const label = t(...labels[state]);
    connection.innerHTML = `<span class="es-connection-dot" aria-hidden="true"></span><span class="es-connection-label">${escape(label)}</span>`;
    const tooltip = refreshing
      ? t('Obnovuji data ze serveru…', 'Refreshing data from the server…')
      : account?.server_last_seen
        ? `${t('Poslední kontakt', 'Last contact')}: ${date(account.server_last_seen)}`
        : t('Čekáme na první kontakt se serverem.', 'Waiting for the first server contact.');
    const refresh = $('#refresh-data');
    refresh.disabled = !account?.link || refreshing;
    refresh.dataset.tooltip = tooltip;
    refresh.title = tooltip;
    refresh.setAttribute('aria-label', `${label}. ${tooltip}`);
  }
  const gameContext = () => ({ t, escape, number, date, panel, currencyIcon, account, table, row, empty, api, render, status });
  function render() {
    document.body.classList.toggle('es-games', route === 'games');
    document.documentElement.lang = lang;
    document.title = successfulOrder ? `${t('Děkujeme za nákup', 'Thank you for your purchase')} — Pantheon` : `${t(...(names[route] || names.overview))} — Pantheon`;
    $('#language').textContent = lang === 'cs' ? 'EN' : 'CZ'; $('#logout').textContent = t('Odhlásit se', 'Sign out'); $('#logout').hidden = !account;
    $('#language-label').textContent = t('Jazyk', 'Language');
    $('#language').setAttribute('aria-label', t('Přepnout do angličtiny', 'Switch to Czech'));
    $('#account-link').setAttribute('aria-label', t('Nastavení účtu', 'Account settings'));
    $('#account-link').title = t('Nastavení účtu', 'Account settings');
    $('#support').textContent = t('Podpora', 'Support');
    menuToggle.setAttribute('aria-label', t('Otevřít navigaci', 'Open navigation'));
    $('#navigation-title').textContent = t('Hráčský účet', 'Player account');
    $('#close-navigation').setAttribute('aria-label', t('Zavřít navigaci', 'Close navigation'));
    $('#navigation').setAttribute('aria-label', t('Hráčský účet', 'Player account'));
    $('#page-title').textContent = successfulOrder ? t('Děkujeme za nákup', 'Thank you for your purchase') : t(...(names[route] || names.overview));
    $('#page-description').textContent = successfulOrder ? t('Tady můžeš sledovat potvrzení platby i doručení na server.', 'Track payment confirmation and server delivery here.') : t('Tvůj Pantheon účet. Postup ve hře, vzhled a nákupy na jednom místě.', 'Your Pantheon account. Game progress, appearance, and purchases in one place.');
    $('#navigation').innerHTML = Object.entries(names).filter(([key]) => key !== 'pair' && (key !== 'tournament-admin' || account?.tournament_admin)).map(([key, labels]) => `<a href="/economysuite/${key}" ${key === route ? 'aria-current="page"' : ''}>${icon(key)}<span>${escape(t(...labels))}</span></a>`).join('');
    $('#player-identity').innerHTML = `<span class="es-avatar" aria-hidden="true">${escape(account?.link?.name?.slice(0, 2).toUpperCase() || 'P')}</span><div><strong>${escape(account?.link?.name || t('Hráčský účet', 'Player account'))}</strong><small>Pantheon Survival</small></div>`;
    renderConnection();
    let html;
    if (route === 'tournament' || route === 'tournament-admin') html = window.ESTournament.render({t,escape,admin:route==='tournament-admin'});
    else if (route === 'games') html = window.ESGames.render(gameContext());
    else if (route === 'store') html = store();
    else if (route === 'rank') html = rankPage() + storePurchaseDialog();
    else if (route === 'pair') html = pairingPage();
    else if (route === 'purchases') html = purchases();
    else if (route === 'settings') html = account ? settings() : empty();
    else if (!account?.link) html = empty();
    else if (!account.snapshot) html = waiting();
    else html = ({ overview, statistics, progress, appearance }[route] || overview)(account.snapshot);
    if (route === 'overview' || route === 'store') html = dailyRewardCard() + html;
    $('#content').innerHTML = html; $('#content').setAttribute('aria-busy', 'false');
    bind();
  }
  async function action(button, work) { feedback?.busy(button, true); try { await work(); } catch (failure) { status(failure.message, true); } finally { if (button.isConnected) feedback?.busy(button, false); } }
  function bind() {
    if(route==='tournament'||route==='tournament-admin')window.ESTournament.bind({api,t,escape,status,admin:route==='tournament-admin'});
    bindDailyReward();
    const rankDialogNode = $('#rank-details-dialog');
    document.querySelectorAll('[data-rank]').forEach(button => button.addEventListener('click', () => {
      const id = button.dataset.rank, content = rankDetail(id);
      if (!content || !rankDialogNode) return;
      rankDialogNode.className = 'es-rank-dialog es-tier-' + id;
      $('#rank-details-content').innerHTML = content;
      rankDialogNode.showModal();
      document.body.classList.add('es-modal-open');
      $('#close-rank-details').focus();
      $('#order-rank')?.addEventListener('click', event => {
        const orderButton = event.currentTarget;
        rankDialogNode.close();
        openPurchaseDialog(button, orderButton.dataset.price);
      });
    }));
    $('#close-rank-details')?.addEventListener('click', () => rankDialogNode.close());
    rankDialogNode?.addEventListener('close', () => document.body.classList.remove('es-modal-open'));
    rankDialogNode?.addEventListener('click', event => { if (event.target === rankDialogNode) { const bounds = rankDialogNode.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) rankDialogNode.close(); } });
    if (route === 'games') window.ESGames.bind(gameContext());
    $('#retry-load')?.addEventListener('click', () => action($('#retry-load'), () => load({ initial: true })));
    document.querySelectorAll('.cosmetic-combined-form select').forEach(select => select.addEventListener('change', () => {
      const cosmetics = account.snapshot.cosmetics || {};
      cosmetics[select.name] = cosmetics[select.name] || [];
      cosmetics[select.name] = cosmetics[select.name].map(entry => ({ ...entry, selected: entry.id === select.value }));
      $('#combined-appearance-preview').innerHTML = combinedPreview(cosmetics);
    }));
    $('#appearance-form')?.addEventListener('submit', event => {
      event.preventDefault();
      const form = event.currentTarget;
      const button = form.querySelector('button');
      if (button.disabled) return;
      // currentTarget is cleared after event dispatch; snapshot every selection
      // before the first await, including when polling replaces the form.
      const selections = ['prefix', 'color', 'aura', 'hat'].map(type => ({ type, id: form.elements[type]?.value || '' }));
      action(button, async () => {
        for (const selection of selections) await api('/api/economysuite/cosmetics', selection);
        status(t('Vzhled čeká na potvrzení serverem.', 'Appearance is waiting for server confirmation.'));
      });
    });
    const openPurchaseDialog = (button, priceId = button.dataset.price) => {
      const pack = packages.find(item => item.id === priceId);
      if (!pack) return;
      pendingPurchase = { pack, button };
      $('#purchase-dialog-summary').innerHTML = '<strong>' + escape(pack.name) + '</strong><span>' + (pack.currency === 'rank' ? rankSymbol(pack.rank_id) : currencyIcon(pack.currency)) + ' ' + productLabel(pack) + '</span><b>' + money(pack.price_minor) + ' CZK</b>';
      $('#purchase-consent-form').reset();
      $('#purchase-dialog').hidden = false;
      document.body.classList.add('es-modal-open');
      $('#confirm-purchase').focus();
    };
    const closePurchaseDialog = () => {
      const returnFocus = pendingPurchase && pendingPurchase.button;
      pendingPurchase = null;
      $('#purchase-dialog').hidden = true;
      document.body.classList.remove('es-modal-open');
      if (returnFocus) returnFocus.focus();
    };
    document.querySelectorAll('.buy').forEach(button => button.addEventListener('click', () => openPurchaseDialog(button)));
    $('#close-purchase-dialog')?.addEventListener('click', closePurchaseDialog);
    $('#cancel-purchase')?.addEventListener('click', closePurchaseDialog);
    document.querySelectorAll('[data-close-purchase]').forEach(element => element.addEventListener('click', closePurchaseDialog));
    $('#purchase-consent-form')?.addEventListener('submit', event => { event.preventDefault(); action($('#confirm-purchase'), async () => {
      if (!pendingPurchase || !event.currentTarget.reportValidity()) return;
      const immediate = $('#request-immediate-delivery').checked;
      const result = await api('/api/economysuite/checkout', { price_id: pendingPurchase.pack.id, displayed_price_minor: Number(pendingPurchase.pack.price_minor), displayed_currency: 'czk', accepted_purchase_terms: $('#accept-purchase-terms').checked, immediate_delivery_requested: immediate, withdrawal_rights_acknowledged: immediate, policy_versions: { privacy: '2026-10-06', purchase: '2026-10-06', refund: '2026-10-06', delivery: '2026-10-06' }, idempotency_key: pendingPurchase.pack.id + '-' + crypto.randomUUID() });
      location.assign(result.url);
    }); });
    $('#purchase-dialog')?.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); closePurchaseDialog(); } });
    $('#purchase-filter')?.addEventListener('change', event => { purchaseFilter = event.target.value; render(); });
    $('#privacy-form')?.addEventListener('submit', event => { event.preventDefault(); action(event.currentTarget.querySelector('button'), async () => { await api('/api/economysuite/privacy', { leaderboard: $('#leaderboard-opt-in').checked }); status(t('Soukromí uloženo.', 'Privacy saved.'), false, 'success'); }); });
    $('#unlink-form')?.addEventListener('submit', event => { event.preventDefault(); action(event.currentTarget.querySelector('button'), async () => { await api('/api/economysuite/unlink', { password: $('#unlink-password').value }); await load(); status(t('Hráč byl odpojen.', 'Player unlinked.'), false, 'success'); }); });
    $('#password-form')?.addEventListener('submit', event => { event.preventDefault(); action(event.currentTarget.querySelector('button'), async () => { if ($('#new-password').value !== $('#confirm-password').value) throw new Error(t('Hesla se neshodují.', 'Passwords do not match.')); await api('/api/portal/password/change', { current_password: $('#current-password').value, new_password: $('#new-password').value }); event.target.reset(); status(t('Heslo změněno.', 'Password changed.'), false, 'success'); }); });
    $('#export-data')?.addEventListener('click', event => action(event.currentTarget, async () => { const result = await api('/api/portal/data-export'); const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'tomaspisar-data-export.json'; link.click(); URL.revokeObjectURL(url); status(t('Export byl připraven.', 'Your export is ready.'), false, 'success'); }));
    $('#deletion-form')?.addEventListener('submit', event => { event.preventDefault(); action(event.currentTarget.querySelector('button'), async () => { const approve = window.LJR_FEEDBACK?.['confirm'] ? await window.LJR_FEEDBACK['confirm']({ title: t('Výmaz účtu', 'Account deletion'), description: t('Žádost se zaznamená a provozovatel ji posoudí s ohledem na platby, účetnictví a bezpečnost.', 'The request will be recorded and reviewed with payment, accounting, and security retention in mind.'), confirmLabel: t('Požádat o výmaz', 'Request deletion'), cancelLabel: t('Zrušit', 'Cancel'), destructive: true }) : true; if (!approve) return; await api('/api/portal/account/deletion-request', { password: $('#deletion-password').value }); event.target.reset(); status(t('Žádost o výmaz byla zaznamenána.', 'Deletion request recorded.'), false, 'success'); }); });
    $('#ranking-metric')?.addEventListener('change', async event => { metric = event.target.value; try { rankings = (await api('/api/economysuite/leaderboard?metric=' + metric)).entries; render(); } catch (failure) { status(failure.message, true); } });
    $('#approve-pair')?.addEventListener('click', event => action(event.currentTarget, async () => { const result = await api('/api/economysuite/pair/approve', { token: pairingToken }); pairConfirmation = result.command; sessionStorage.setItem('es-pair-confirmation', pairConfirmation); sessionStorage.removeItem('es-pair'); pairingToken = ''; render(); }));
    $('#copy-pair-command')?.addEventListener('click', async () => { try { await navigator.clipboard.writeText(pairConfirmation); status(t('Příkaz byl zkopírován. Vlož ho do Minecraftu.', 'Command copied. Paste it into Minecraft.'), false, 'success'); } catch { status(t('Kopírování se nepodařilo. Označ příkaz ručně.', 'Copying failed. Select the command manually.'), true); } });
  }
  $('#refresh-data').addEventListener('click', async () => {
    const button = $('#refresh-data');
    if (!account?.link || refreshBaseline !== null) return;
    refreshBaseline = Number(account?.synced_at || 0); refreshStarted = Date.now(); renderConnection(); feedback?.busy(button, true);
    try {
      const refreshWork = api('/api/economysuite/refresh', {}).then(result => {
        refreshOperation = result.operation_id;
        return new Promise((resolve, reject) => { finishRefresh = { resolve, reject }; });
      });
      await (feedback?.promise ? feedback.promise(refreshWork, {
        loading: t('Obnovuji data ze serveru…', 'Refreshing data from the server…'),
        success: t('Data byla obnovena ze serveru.', 'Data refreshed from the server.'),
        error: failure => failure.message
      }) : refreshWork);
      if (!feedback?.promise) status(t('Data byla obnovena ze serveru.', 'Data refreshed from the server.'), false, 'success');
    } catch (failure) { if (!feedback?.promise) status(failure.message, true); }
    finally { refreshBaseline = null; refreshOperation = ''; finishRefresh = null; feedback?.busy(button, false); renderConnection(); }
  });
  async function load(options = {}) {
    const initial = options.initial ?? !account;
    if (initial) { $('#content').setAttribute('aria-busy', 'true'); $('#content').innerHTML = loading(); }
    let accountFailure = null;
    try { account = await api('/api/economysuite/account'); }
    catch (failure) { if (failure.status === 401 && !['store', 'pair', 'rank'].includes(route)) { location.replace(`/login?product=economysuite&next=${encodeURIComponent(location.pathname)}`); return; } if (failure.status !== 401) accountFailure = failure; }
    if (accountFailure && !['store', 'pair', 'rank'].includes(route)) { $('#content').innerHTML = loadError(accountFailure); $('#content').setAttribute('aria-busy', 'false'); bind(); if (options.refresh) throw accountFailure; status(accountFailure.message, true); return; }
    try {
      if ((route === 'tournament' || route === 'tournament-admin') && account) await window.ESTournament.load(api);
      if (route === 'games' && account) await window.ESGames.load(api, account);
      if (route === 'store' || route === 'rank') { const catalog = await api('/api/economysuite/catalog'); packages = catalog.packages; purchasesEnabled = catalog.purchases_enabled; }
      if (route === 'purchases' && account) orders = (await api('/api/economysuite/orders')).orders;
      if (route === 'statistics' && account) rankings = (await api(`/api/economysuite/leaderboard?metric=${metric}`)).entries;
      if (route === 'pair' && account && pairingToken) pairing = await api('/api/economysuite/pair/inspect', { token: pairingToken });
    } catch (failure) { $('#content').innerHTML = loadError(failure); $('#content').setAttribute('aria-busy', 'false'); bind(); if (options.refresh) throw failure; status(failure.message, true); return; }
    render();
  }
  $('#language').addEventListener('click', () => { lang = lang === 'cs' ? 'en' : 'cs'; localStorage.setItem('es-language', lang); render(); });
  $('#logout').addEventListener('click', () => action($('#logout'), async () => { await api('/api/portal/logout', {}); location.assign('/login?product=economysuite'); }));
  load();
  setInterval(async () => {
    if (document.hidden) return;
    try {
      const latest = await api('/api/economysuite/account');
      const dailyChanged = JSON.stringify(account?.daily_reward) !== JSON.stringify(latest.daily_reward) || !!account?.link !== !!latest.link;
      const rankChanged = JSON.stringify(account?.snapshot?.rank) !== JSON.stringify(latest.snapshot?.rank);
      account = latest; renderConnection();
      if (dailyChanged && !dailyClaimPending) refreshDailyReward();
      if (rankChanged || (latest.snapshot?.rank?.id && Number(latest.snapshot.rank.expires_at) <= Date.now())) {
        const rankHost = $('.es-rank-section');
        if (rankHost) rankHost.outerHTML = rankPanel(latest.snapshot || {});
      }
      if (route === 'games') await window.ESGames.poll(gameContext());
      if (finishRefresh && latest.refresh_operation?.id === refreshOperation && latest.refresh_operation.state === 'complete') {
        try { await load({ refresh: true }); finishRefresh.resolve(); }
        catch (failure) { finishRefresh.reject(failure); }
        return;
      }
      if (finishRefresh && latest.refresh_operation?.id === refreshOperation && latest.refresh_operation.state === 'failed') finishRefresh.reject(new Error(t('Server nedokázal obnovit data. Zkus to znovu.', 'The server could not refresh the data. Try again.')));
      if (finishRefresh && Date.now() - refreshStarted > 45000) finishRefresh.reject(new Error(t('Server zatím nová data neposlal. Zkus obnovení později.', 'The server has not sent fresh data yet. Try again later.')));
      if (successfulOrder) { orders = (await api('/api/economysuite/orders')).orders; render(); }
    } catch { if (account) account.server_status = 'disconnected'; finishRefresh?.reject(new Error(t('Server neodpovídá. Zkus obnovit znovu.', 'The server is not responding. Try refreshing again.'))); renderConnection(); }
  }, 5000);
})();
