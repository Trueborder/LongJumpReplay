(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let lang = localStorage.getItem('es-language') === 'en' ? 'en' : 'cs';
  let account = null, packages = [], purchasesEnabled = false, orders = [], rankings = [], metric = 'playtime';
  let refreshBaseline = null, refreshStarted = 0;
  const route = location.pathname.split('/')[2] || 'overview';
  const successfulOrder = route === 'purchases' && /^[a-f0-9-]{36}$/i.test(new URLSearchParams(location.search).get('order') || '') ? new URLSearchParams(location.search).get('order') : '';
  const names = { overview: ['Přehled', 'Overview'], statistics: ['Statistiky', 'Statistics'], progress: ['Postup', 'Progress'], appearance: ['Vzhled', 'Appearance'], store: ['Obchod', 'Store'], purchases: ['Nákupy', 'Purchases'], settings: ['Nastavení', 'Settings'], pair: ['Propojení účtu', 'Pair your account'] };
  const paths = {
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
  const status = (message, failed = false) => { $('#status').textContent = message; $('#status').dataset.error = String(failed); };
  const cookie = name => document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith(`${name}=`))?.split('=').slice(1).join('=') || '';
  const errors = { pair_required: ['Nejdřív propoj svůj Minecraft účet.', 'Pair your Minecraft account first.'], invalid_password: ['Heslo není správné.', 'The password is incorrect.'], pair_expired: ['Propojení vypršelo. Použij znovu /web link.', 'Pairing expired. Run /web link again.'], pending_delivery: ['Nejdřív dokonči čekající nákupy a doručení.', 'Finish pending checkouts and deliveries first.'], already_linked: ['Tento účet nebo hráč už je propojený.', 'This account or player is already linked.'], unavailable: ['Tato funkce zatím není dostupná.', 'This feature is not available yet.'], invalid_confirmation: ['Potvrzení není platné.', 'The confirmation is invalid.'] };
  async function api(path, data) {
    const response = await fetch(path, { method: data ? 'POST' : 'GET', credentials: 'include', headers: data ? { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(cookie('ljr-portal-csrf')) } : {}, body: data ? JSON.stringify(data) : undefined });
    const result = await response.json();
    if (!response.ok) {
      const pair = errors[result.error];
      const failure = new Error(pair ? t(...pair) : t('Požadavek se nepodařilo dokončit. Zkus to znovu.', 'The request could not be completed. Please try again.'));
      failure.status = response.status; throw failure;
    }
    return result;
  }
  const panel = (title, content, cls = '') => `<section class="es-panel ${cls}"><h2>${escape(title)}</h2>${content}</section>`;
  const empty = () => panel(t('Tvůj hráčský účet začíná propojením.', 'Your player account starts with pairing.'), `<p>${escape(t('Přihlas se na Pantheon a spusť příkaz. Na webu potvrď hráče a poté dokonči propojení ve hře.', 'Sign in to Pantheon and run the command. Confirm your player on the website, then finish pairing in-game.'))}</p><code>/web link</code>`, 'es-empty');
  const waiting = () => panel(t('Čekáme na první synchronizaci.', 'Waiting for the first sync.'), `<p>${escape(t('Účet je propojený. Přehled se naplní, jakmile se připojí server.', 'Your account is paired. Your overview will populate when the server connects.'))}</p>`);
  const table = (headers, rows) => `<div class="es-table-wrap"><table class="es-table"><thead><tr>${headers.map(h => `<th>${escape(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
  const row = cells => `<tr>${cells.map(c => `<td>${c}</td>`).join('')}</tr>`;
  const statNames = { playtime: ['Doba hraní (min)', 'Playtime (min)'], blocks_mined: ['Vytěžené bloky', 'Blocks mined'], blocks_placed: ['Položené bloky', 'Blocks placed'], mobs_killed: ['Zabití mobové', 'Mobs killed'], deaths: ['Úmrtí', 'Deaths'], crafted: ['Výroba', 'Crafting'], smelted: ['Tavení', 'Smelting'], fish_caught: ['Ulovené ryby', 'Fish caught'], breeding: ['Chov', 'Breeding'], trades: ['Obchody', 'Trades'], items_sold: ['Prodané předměty', 'Items sold'], items_bought: ['Koupené předměty', 'Items bought'], challenges_won: ['Vyhrané výzvy', 'Challenges won'], tasks_completed: ['Dokončené úkoly', 'Completed tasks'], crates_opened: ['Otevřené crates', 'Crates opened'], daily_claims: ['Denní odměny', 'Daily claims'], passive_job_coins: ['Výdělek z profese', 'Job income'], duel_wins: ['Výhry v duelech', 'Duel wins'], duel_losses: ['Prohry v duelech', 'Duel losses'], duel_draws: ['Remízy v duelech', 'Duel draws'], duel_damage: ['Poškození v duelech', 'Duel damage'] };
  const metricCard = (title, value, note, currency = '') => `<section class="es-panel es-metric"><div class="es-metric-heading">${currency ? currencyIcon(currency) : icon('statistics')}<small>${escape(title)}</small></div><strong>${number(value)}</strong><span class="es-label">${escape(note)}</span></section>`;
  function overview(snapshot) {
    const level = snapshot.level || {};
    const debt = Number(snapshot.debt?.coins || 0) + Number(snapshot.debt?.tokens || 0);
    return `<div class="es-grid">${metricCard('Coins', snapshot.coins, t('Dostupný zůstatek', 'Available balance'), 'coins')}${metricCard('Tokens', snapshot.tokens, `${t('Čekající', 'Pending')}: ${number(snapshot.pending_tokens)}`, 'tokens')}${metricCard(t('Aktivní minuty', 'Active minutes'), snapshot.active_minutes, t('Počítá se pouze hra na serveru', 'Only server gameplay counts'))}</div>` +
      panel(t('Tvoje úroveň', 'Your level'), `<div class="es-level"><span class="es-level-number">${number(level.level || 1)}</span><div><strong>${number(level.xp)} XP</strong><p>${escape(t('XP a odměny získáváš hraním na Pantheonu.', 'Earn XP and rewards by playing on Pantheon.'))}</p></div></div>`) +
      panel(t('Profese a odměny', 'Job and rewards'), `<div class="es-detail"><span>${t('Profese', 'Job')}</span><strong>${escape(strip(snapshot.job?.display || snapshot.job?.id || t('Nevybraná', 'Not selected')))}</strong></div><div class="es-detail"><span>${t('Úroveň profese', 'Job level')}</span><strong>${number(snapshot.job?.level)}</strong></div><div class="es-detail"><span>${t('Denní kalendář', 'Daily calendar')}</span><strong>${number(snapshot.daily?.day)} / 30</strong></div><p>${escape(t('Odměny si vyzvedni ve hře. Webová aktivita nepřidává aktivní čas ani tokeny.', 'Claim rewards in-game. Website activity does not add active time or tokens.'))}</p>`) +
      (debt ? panel(t('Dluh po vrácení platby', 'Refund debt'), `<p>${number(snapshot.debt.coins)} coins · ${number(snapshot.debt.tokens)} tokens</p><p>${escape(t('Utrácení a převody jsou pozastavené, dokud dluh nesplatíš. Další příjmy nejdřív splácejí dluh příslušné měny.', 'Spending and transfers are paused until the debt is settled. Future income first pays down debt in the same currency.'))}</p>`) : '');
  }
  function statistics(snapshot) {
    const stats = snapshot.statistics || {};
    return panel(t('Tvoje statistiky', 'Your statistics'), table([t('Statistika', 'Statistic'), t('Celkem', 'All time'), t('Tento týden', 'This week')], Object.keys(statNames).map(key => row([escape(t(...statNames[key])), number(stats.all_time?.[key]), number(stats.weekly?.[key])])))) +
      panel(t('Žebříček hráčů, kteří souhlasili se zveřejněním', 'Opt-in player rankings'), `<div class="es-controls"><label for="ranking-metric">${t('Porovnat', 'Compare')}</label><select id="ranking-metric">${['playtime', 'blocks_mined', 'tasks_completed', 'duel_wins'].map(key => `<option value="${key}" ${key === metric ? 'selected' : ''}>${escape(t(...statNames[key]))}</option>`).join('')}</select></div>${rankings.length ? table(['#', t('Hráč', 'Player'), t('Hodnota', 'Value')], rankings.map((entry, i) => row([number(i + 1), escape(entry.name), number(entry.value)]))) : `<p>${t('Zatím žádní hráči.', 'No players yet.')}</p>`}<p>${escape(t('Zůstatky ani nákupy se nezveřejňují. Účast změníš v Nastavení.', 'Balances and purchases remain private. Change participation in Settings.'))}</p>`);
  }
  function progress(snapshot) {
    const tasks = snapshot.progress?.tasks || [];
    const achievements = snapshot.progress?.achievements || [];
    const jobs = snapshot.progress?.chapters || [];
    return panel(t('Aktuální úkoly', 'Current tasks'), tasks.length ? table([t('Úkol', 'Task'), t('Postup', 'Progress'), t('Stav', 'State')], tasks.map(task => row([escape(strip(task.name || task.id)), `${number(task.progress)} / ${number(task.target)}`, task.complete ? t('Dokončeno', 'Complete') : t('Probíhá', 'In progress')]))) : `<p>${t('Aktivní úkoly se zobrazí po připojení do hry.', 'Active tasks will appear after joining the game.')}</p>`) +
      panel(t('Profese a achievementy', 'Jobs and achievements'), `<p>${escape(t('Vyzvednuté kapitoly aktuální profese', 'Claimed chapters in your current job'))}: ${jobs.map(number).join(', ') || '—'}</p><p>${escape(t('Dokončené achievementy', 'Completed achievements'))}: ${achievements.map(a => escape(strip(a.name || a))).join(', ') || '—'}</p>`) +
      panel(t('Denní kalendář', 'Daily calendar'), `<p>${t('Den', 'Day')} ${number(snapshot.daily?.day)} / 30 · Revive: ${number(snapshot.daily?.revives)} · ${t('Poslední odměna', 'Last claim')}: ${escape(snapshot.daily?.last_day || '—')}</p><div class="es-calendar">${Array.from({ length: 30 }, (_, i) => `<span class="${i < Number(snapshot.daily?.day || 0) ? 'earned' : ''}">${i + 1}</span>`).join('')}</div><p>${t('Odměny a obnovu série spravuj ve hře přes /daily. Reset je o půlnoci Europe/Prague.', 'Manage rewards and streak recovery in-game with /daily. Reset is at midnight Europe/Prague.')}</p>`) +
      panel(t('Tokeny za aktivní hru', 'Active-play tokens'), `<p>${snapshot.eligible ? t('Převody tokenů jsou odemčené.', 'Token transfers are unlocked.') : t('Převody vyžadují stáří účtu 48 hodin a 300 aktivních minut.', 'Transfers require an account age of 48 hours and 300 active minutes.')}</p><p>${t('Placené tokeny můžeš utrácet ihned. Omezení převodů zůstává stejné.', 'Paid tokens can be spent immediately. Transfer eligibility remains unchanged.')}</p>`);
  }
  function appearance(snapshot) {
    const cosmetics = snapshot.cosmetics || {};
    return ['prefix', 'color', 'title'].map(type => {
      const entries = cosmetics[type] || [];
      return panel(t(...({ prefix: ['Prefix', 'Prefix'], color: ['Barva chatu', 'Chat colour'], title: ['Titul', 'Title'] }[type])), `<form class="es-form cosmetic-form" data-type="${type}"><label for="cosmetic-${type}">${t('Vybrat odemčený vzhled', 'Choose an unlocked appearance')}</label><select id="cosmetic-${type}" name="id"><option value="">${t('Vypnuto', 'Off')}</option>${entries.filter(e => e.owned).map(e => `<option value="${escape(e.id)}" ${e.selected ? 'selected' : ''}>${escape(strip(e.display || e.id))}</option>`).join('')}</select><div class="es-preview">${preview(type, entries.find(e => e.selected))}</div><button type="submit">${t('Použít', 'Apply')}</button></form>${entries.some(e => !e.owned) ? `<p class="es-muted">${t('Další vzhledy odemkneš ve hře.', 'Unlock more appearances in-game.')}</p>` : ''}`);
    }).join('') + panel(t('Synchronizace změn', 'Change synchronization'), `<p>${t('Změny se použijí po potvrzení serverem. Když je server vypnutý, zůstanou čekat.', 'Changes apply after server confirmation. When the server is stopped, they remain queued.')}</p>${(account.cosmetic_operations || []).map(op => `<p class="es-muted">${escape(op.id.slice(0, 8))}: ${escape(op.state === 'pending' ? t('Čeká na server', 'Waiting for server') : op.state === 'failed' ? t('Změnu se nepodařilo použít', 'Change could not be applied') : t('Použito', 'Applied'))}</p>`).join('')}`);
  }
  function store() {
    const support = `<div class="es-panel es-support-note"><p><strong>${t('Podpora vývoje', 'Support the developer')}</strong></p><p>${t('Všechny peníze z tohoto obchodu jdou přímo vývojáři Tomáši Pisárovi a pomáhají mu financovat vývoj, údržbu a provoz EconomySuite. Děkuji za podporu.', 'All money from this store goes directly to developer Tomáš Pisár and helps fund EconomySuite development, maintenance, and operation. Thank you for your support.')}</p></div>`;
    const legal = `<form id="purchase-consent-form" class="es-purchase-consent"><p><strong>${t('Před platbou si zkontroluj objednávku', 'Review your order before payment')}</strong></p><label class="es-inline"><input id="accept-purchase-terms" type="checkbox">${t('Souhlasím s <a href="https://tomaspisar.cz/legal/economysuite-purchases/" target="_blank" rel="noopener">podmínkami nákupu EconomySuite</a>.', 'I accept the <a href="https://tomaspisar.cz/legal/economysuite-purchases/" target="_blank" rel="noopener">EconomySuite purchase terms</a>.')}</label><label class="es-inline"><input id="request-immediate-delivery" type="checkbox">${t('Výslovně žádám o okamžité digitální dodání po potvrzení platby a beru na vědomí ztrátu práva na odstoupení v rozsahu povoleném právními předpisy.', 'I expressly request immediate digital delivery after payment confirmation and acknowledge the loss of the withdrawal right to the extent permitted by law.')}</label><p class="es-muted">${t('Cena je uvedena v CZK. DPH/VAT: režim a zahrnutí DPH doplní provozovatel. Dodání: po potvrzení platby, obvykle během několika sekund; při offline serveru čeká ve frontě. ', 'Prices are shown in CZK. VAT: the operator must complete the applicable VAT treatment. Delivery: after payment confirmation, usually within seconds; if the server is offline, it remains queued. ')}<a href="https://tomaspisar.cz/legal/refunds/" target="_blank" rel="noopener">${t('Vrácení a odstoupení', 'Refunds and withdrawal')}</a>.</p></form>`;
    return `${support}<div class="es-panel"><p>${escape(t('Jednorázové balíčky pro tvůj propojený účet na Pantheonu. Coins a tokens nemají peněžní hodnotu, nelze je vybrat ani převést na jiný server a nákup neslibuje výhodu pay-to-win.', 'One-time packages for your paired Pantheon account. Coins and tokens have no monetary value, cannot be cashed out or transferred to another server, and purchases do not promise pay-to-win advantages.'))}</p><p>${escape(t('Hráč může být offline. Pokud server neběží, zaplacený balíček počká na doručení.', 'Your player can be offline. If the server is stopped, a paid package waits for delivery.'))}</p></div>${legal}` +
      (packages.length ? `<div class="es-grid">${packages.map(pack => panel(pack.name, `<div class="es-pack-amount">${currencyIcon(pack.currency)}<span>${number(pack.amount)} ${escape(pack.currency)}</span></div><p>${escape(pack.description)}</p><span class="es-pack-price">${money(pack.price_minor)} <small>CZK</small></span><p class="es-muted">${t('Digitální obsah · bez dopravy · dodání po potvrzení platby', 'Digital content · no shipping · delivery after payment confirmation')}</p><button class="es-primary buy" data-price="${escape(pack.id)}" data-amount="${pack.price_minor}" ${!purchasesEnabled || !account?.link ? 'disabled' : ''}>${icon('store')}${t('Objednávka zavazující k platbě', 'Order obligating to pay')}</button>`, 'es-pack')).join('')}</div>` : panel(t('Obchod se připravuje.', 'The store is being prepared.'), `<p>${escape(t('Balíčky a ceny zde budou zveřejněné před otevřením prodeje.', 'Packages and prices will be published here before sales open.'))}</p>`, 'es-empty')) +
      (!account?.link ? `<p>${t('Pro nákup se přihlas a propoj hráče.', 'Sign in and pair your player to purchase.')} <a href="/login?product=economysuite">${t('Přihlásit se', 'Sign in')}</a></p>` : '');
  }
  function purchases() {
    const labels = { checkout: ['Čeká na platbu', 'Awaiting payment'], cancelled: ['Zrušeno', 'Cancelled'], paid: ['Zaplaceno', 'Paid'], refunded: ['Vráceno', 'Refunded'], partially_refunded: ['Částečně vráceno', 'Partially refunded'], disputed: ['Spor o platbu', 'Payment dispute'] };
    const thanks = successfulOrder ? thankYou(orders.find(order => order.id === successfulOrder)) : '';
    return thanks + panel(t('Historie nákupů', 'Purchase history'), orders.length ? table([t('Datum', 'Date'), t('Balíček', 'Package'), t('Cena', 'Price'), t('Stav', 'Status'), t('Doklad', 'Receipt')], orders.map(order => {
      const receipt = /^https:\/\/(pay|invoice|dashboard)\.stripe\.com\//.test(order.receipt_url || '') ? `<a href="${escape(order.receipt_url)}" rel="noopener" target="_blank">${t('Otevřít', 'Open')}</a>` : '—';
      const delivery = order.revision > 0 ? order.delivered_revision >= order.revision ? t('Potvrzeno serverem', 'Confirmed by server') : t('Čeká na server', 'Waiting for server') : '';
      const confirmation = order.order_confirmation_sent_at ? t('Potvrzení e-mailem', 'Email confirmation') : t('Potvrzení čeká', 'Confirmation pending');
      return row([escape(date(order.created_at)), `<span class="es-order-item">${currencyIcon(order.currency_type)}<span>${number(order.currency_amount)} ${escape(order.currency_type)}<br><span class="es-muted">${escape(order.player_name)}</span></span></span>`, money(order.price_minor), `${escape(t(...(labels[order.state] || [order.state, order.state])))}<br><span class="es-muted">${escape(delivery)}</span>`, `${receipt}<br><span class="es-muted">${escape(confirmation)}</span>`]);
    })) : `<p>${t('Zatím nemáš žádné nákupy.', 'You have no purchases yet.')}</p>`);
  }
  function thankYou(order) {
    const paid = order && order.revision > 0, delivered = paid && order.delivered_revision >= order.revision;
    const state = delivered ? 'delivered' : paid ? 'delivering' : 'confirming';
    const heading = delivered ? t('Děkujeme! Nákup je ve hře.', 'Thank you! Your purchase is in-game.') : paid ? t('Děkujeme za nákup.', 'Thank you for your purchase.') : t('Děkujeme. Ověřujeme platbu.', 'Thank you. We are confirming your payment.');
    const detail = delivered ? t('Server doručení potvrdil. Zůstatek uvidíš přes /money nebo /tokens.', 'The server confirmed delivery. Check your balance with /money or /tokens.') : paid ? t('Platba je potvrzená a server balíček doručuje. Obvykle to trvá do pěti sekund.', 'Payment is confirmed and the server is delivering your package. This usually takes up to five seconds.') : t('Stripe nás právě vrací k objednávce. Potvrzení může trvat až 30 sekund; stránku můžeš bezpečně opustit.', 'Stripe is returning you to the order. Confirmation can take up to 30 seconds; you may safely leave this page.');
    const item = order ? `<div class="es-thanks-item">${currencyIcon(order.currency_type)}<strong>${number(order.currency_amount)} ${escape(order.currency_type)}</strong><span>${money(order.price_minor)}</span></div>` : '';
    return `<section class="es-thanks" data-state="${state}"><div class="es-thanks-check" aria-hidden="true">${delivered ? '✓' : '···'}</div><div><p class="es-eyebrow">STRIPE / PANTHEON</p><h2>${heading}</h2><p>${detail}</p>${item}<ol><li>${t('Připoj se na Pantheon.', 'Join Pantheon.')}</li><li>${t('Otevři chat a použij /money nebo /tokens.', 'Open chat and use /money or /tokens.')}</li><li>${t('Když je server offline, nákup zůstane bezpečně čekat.', 'If the server is offline, the purchase remains safely queued.')}</li></ol></div></section>`;
  }
  function settings() {
    return panel(t('Propojený hráč', 'Paired player'), account.link ? `<p><strong>${escape(account.link.name)}</strong><br><span class="es-muted">${escape(account.link.uuid)}</span></p><form id="unlink-form" class="es-form"><label for="unlink-password">${t('Potvrď odpojení heslem k webovému účtu', 'Confirm unlinking with your website password')}</label><input id="unlink-password" type="password" autocomplete="current-password" required><button type="submit" class="es-danger">${t('Odpojit hráče', 'Unlink player')}</button></form>` : empty()) +
      (account.link ? panel(t('Soukromí', 'Privacy'), `<form id="privacy-form" class="es-form"><label class="es-inline"><input id="leaderboard-opt-in" type="checkbox" ${account.link.leaderboard ? 'checked' : ''}>${t('Zveřejnit Minecraft jméno a vybrané statistiky v žebříčku', 'Publish my Minecraft name and selected statistics in rankings')}</label><p>${t('Zůstatky, e-mail a nákupy zůstávají soukromé.', 'Balances, email, and purchases remain private.')}</p><button type="submit">${t('Uložit', 'Save')}</button></form>`) : '') +
      panel(t('Heslo k účtu', 'Account password'), `<form id="password-form" class="es-form"><label for="current-password">${t('Současné heslo', 'Current password')}</label><input id="current-password" type="password" autocomplete="current-password" required><label for="new-password">${t('Nové heslo', 'New password')}</label><input id="new-password" type="password" autocomplete="new-password" minlength="12" required><label for="confirm-password">${t('Potvrdit nové heslo', 'Confirm new password')}</label><input id="confirm-password" type="password" autocomplete="new-password" minlength="12" required><p>${t('Alespoň 12 znaků, písmeno, číslo a symbol.', 'At least 12 characters, a letter, a number, and a symbol.')}</p><button type="submit">${t('Změnit heslo', 'Change password')}</button></form>`) + panel(t('Moje data', 'My data'), `<p>${t('Stáhni si kopii údajů účtu a požádej o výmaz po ověření heslem. Platební, účetní a bezpečnostní údaje mohou zůstat uchované podle práva.', 'Download a copy of your account data and request deletion after password verification. Payment, accounting, and security records may need to remain under law.')}</p><div class="es-button-row"><button id="export-data" type="button">${t('Exportovat data', 'Export data')}</button></div><form id="deletion-form" class="es-form"><label for="deletion-password">${t('Heslo pro žádost o výmaz', 'Password for deletion request')}</label><input id="deletion-password" type="password" autocomplete="current-password" required><button type="submit" class="es-danger">${t('Požádat o výmaz účtu', 'Request account deletion')}</button></form>`) + panel('Podpora / Support', `<p>${escape(account.email)}</p><a href="https://tomaspisar.cz/contact/?product=economysuite">${t('Nahlásit problém', 'Report a problem')}</a>`);
  }
  let pairing = null, pairingToken = '', pairConfirmation = '';
  try {
    const fragment = new URLSearchParams(location.hash.slice(1)).get('pair');
    if (fragment && /^[A-Za-z0-9_-]{20,256}$/.test(fragment)) { sessionStorage.setItem('es-pair', JSON.stringify({ token: fragment, expires: Date.now() + 300000 })); history.replaceState({}, '', location.pathname + location.search); }
    const pending = JSON.parse(sessionStorage.getItem('es-pair') || 'null');
    if (pending?.expires > Date.now()) pairingToken = pending.token; else sessionStorage.removeItem('es-pair');
  } catch { /* pairing can be restarted in-game */ }
  function pairingPage() {
    if (!account) return panel(t('Přihlas se a potvrď propojení.', 'Sign in to confirm pairing.'), `<a class="es-button es-primary" href="/login?product=economysuite&next=/economysuite/pair">${t('Přihlásit se', 'Sign in')}</a>`);
    if (account.link) return panel(t('Účet je propojený.', 'Your account is paired.'), `<p>${escape(account.link.name)}</p><a class="es-button es-primary" href="/economysuite/overview">${t('Otevřít přehled', 'Open overview')}</a>`);
    if (pairConfirmation) return panel(t('Dokonči propojení ve hře.', 'Finish pairing in-game.'), `<code class="es-command">${escape(pairConfirmation)}</code><p>${t('Kód platí pět minut od spuštění /web link.', 'The code expires five minutes after starting /web link.')}</p>`);
    if (!pairing) return empty();
    return panel(t('Propojit hráče', 'Pair player'), `<h2>${escape(pairing.name)}</h2><p>${t('Potvrď pouze hráče, který je tvůj. Po potvrzení zde získáš příkaz pro dokončení ve hře.', 'Confirm only your own player. You will receive a command to finish pairing in-game.')}</p><button id="approve-pair" class="es-primary">${t('Potvrdit hráče', 'Confirm player')}</button><div id="pair-command"></div>`);
  }
  function renderConnection() {
    const state = account?.server_status || 'connecting';
    const labels = { connected: ['Server je připojený', 'Server connected'], connecting: ['Server se připojuje…', 'Server connecting…'], disconnected: ['Server je odpojený', 'Server disconnected'] };
    const connection = $('#connection');
    connection.dataset.state = state;
    connection.innerHTML = `<span class="es-connection-dot" aria-hidden="true"></span><span>${escape(t(...labels[state]))}</span>`;
    connection.title = account?.server_last_seen ? `${t('Poslední kontakt', 'Last contact')}: ${date(account.server_last_seen)}` : t('Čekáme na první kontakt se serverem.', 'Waiting for the first server contact.');
    const refresh = $('#refresh-data');
    refresh.hidden = !account?.link;
    refresh.disabled = refreshBaseline !== null;
    refresh.querySelector('span').textContent = refreshBaseline !== null ? t('Obnovuji…', 'Refreshing…') : t('Obnovit data', 'Refresh data');
  }
  function render() {
    document.documentElement.lang = lang;
    document.title = successfulOrder ? `${t('Děkujeme za nákup', 'Thank you for your purchase')} — Pantheon` : `${t(...(names[route] || names.overview))} — Pantheon`;
    $('#language').textContent = lang === 'cs' ? 'EN' : 'CZ'; $('#logout').textContent = t('Odhlásit se', 'Sign out'); $('#logout').hidden = !account;
    $('#support').textContent = t('Podpora', 'Support');
    $('#page-title').textContent = successfulOrder ? t('Děkujeme za nákup', 'Thank you for your purchase') : t(...(names[route] || names.overview));
    $('#page-description').textContent = successfulOrder ? t('Tady můžeš sledovat potvrzení platby i doručení na server.', 'Track payment confirmation and server delivery here.') : t('Tvůj Pantheon účet. Postup ve hře, vzhled a nákupy na jednom místě.', 'Your Pantheon account. Game progress, appearance, and purchases in one place.');
    $('#navigation').innerHTML = Object.entries(names).filter(([key]) => key !== 'pair').map(([key, labels]) => `<a href="/economysuite/${key}" ${key === route ? 'aria-current="page"' : ''}>${icon(key)}<span>${escape(t(...labels))}</span></a>`).join('');
    $('#player-identity').innerHTML = `<span class="es-avatar" aria-hidden="true">${escape(account?.link?.name?.slice(0, 2).toUpperCase() || 'P')}</span><div><strong>${escape(account?.link?.name || t('Hráčský účet', 'Player account'))}</strong><small>Pantheon Survival</small></div>`;
    renderConnection();
    let html;
    if (route === 'store') html = store();
    else if (route === 'pair') html = pairingPage();
    else if (route === 'purchases') html = purchases();
    else if (route === 'settings') html = account ? settings() : empty();
    else if (!account?.link) html = empty();
    else if (!account.snapshot) html = waiting();
    else html = ({ overview, statistics, progress, appearance }[route] || overview)(account.snapshot);
    $('#content').innerHTML = html; $('#content').setAttribute('aria-busy', 'false');
    bind();
  }
  async function action(button, work) { button.disabled = true; try { await work(); } catch (failure) { status(failure.message, true); } finally { if (button.isConnected) button.disabled = false; } }
  function bind() {
    document.querySelectorAll('.cosmetic-form select').forEach(select => select.addEventListener('change', () => { const form = select.closest('form'), type = form.dataset.type; const entry = account.snapshot.cosmetics[type].find(e => e.id === select.value && e.owned); form.querySelector('.es-preview').innerHTML = preview(type, entry); }));
    const purchaseForm = $('#purchase-consent-form');
    const updatePurchaseButtons = () => { const ready = Boolean($('#accept-purchase-terms')?.checked && $('#request-immediate-delivery')?.checked); document.querySelectorAll('.buy').forEach(button => { button.disabled = button.disabled && !account?.link ? true : !ready || !purchasesEnabled || !account?.link; }); };
    purchaseForm?.addEventListener('change', updatePurchaseButtons); updatePurchaseButtons();
    document.querySelectorAll('.buy').forEach(button => button.addEventListener('click', () => action(button, async () => { if (!purchaseForm?.reportValidity?.()) return; const result = await api('/api/economysuite/checkout', { price_id: button.dataset.price, displayed_price_minor: Number(button.dataset.amount), displayed_currency: 'czk', accepted_purchase_terms: true, immediate_delivery_requested: true, withdrawal_rights_acknowledged: true, policy_versions: { privacy: '2026-10-06', purchase: '2026-10-06', refund: '2026-10-06', delivery: '2026-10-06' }, idempotency_key: `${button.dataset.price}-${crypto.randomUUID()}` }); location.assign(result.url); })));
    document.querySelectorAll('.cosmetic-form').forEach(form => form.addEventListener('submit', event => { event.preventDefault(); action(form.querySelector('button'), async () => { await api('/api/economysuite/cosmetics', { type: form.dataset.type, id: form.elements.id.value }); status(t('Změna čeká na potvrzení serverem.', 'Change is waiting for server confirmation.')); }); }));
    $('#privacy-form')?.addEventListener('submit', event => { event.preventDefault(); action(event.currentTarget.querySelector('button'), async () => { await api('/api/economysuite/privacy', { leaderboard: $('#leaderboard-opt-in').checked }); status(t('Soukromí uloženo.', 'Privacy saved.')); }); });
    $('#unlink-form')?.addEventListener('submit', event => { event.preventDefault(); action(event.currentTarget.querySelector('button'), async () => { await api('/api/economysuite/unlink', { password: $('#unlink-password').value }); await load(); status(t('Hráč byl odpojen.', 'Player unlinked.')); }); });
    $('#password-form')?.addEventListener('submit', event => { event.preventDefault(); action(event.currentTarget.querySelector('button'), async () => { if ($('#new-password').value !== $('#confirm-password').value) throw new Error(t('Hesla se neshodují.', 'Passwords do not match.')); await api('/api/portal/password/change', { current_password: $('#current-password').value, new_password: $('#new-password').value }); event.target.reset(); status(t('Heslo změněno.', 'Password changed.')); }); });
    $('#export-data')?.addEventListener('click', event => action(event.currentTarget, async () => { const result = await api('/api/portal/data-export'); const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'tomaspisar-data-export.json'; link.click(); URL.revokeObjectURL(url); status(t('Export byl připraven.', 'Your export is ready.')); }));
    $('#deletion-form')?.addEventListener('submit', event => { event.preventDefault(); action(event.currentTarget.querySelector('button'), async () => { const approve = window.LJR_FEEDBACK?.['confirm'] ? await window.LJR_FEEDBACK['confirm']({ title: t('Výmaz účtu', 'Account deletion'), description: t('Žádost se zaznamená a provozovatel ji posoudí s ohledem na platby, účetnictví a bezpečnost.', 'The request will be recorded and reviewed with payment, accounting, and security retention in mind.'), confirmLabel: t('Požádat o výmaz', 'Request deletion'), cancelLabel: t('Zrušit', 'Cancel'), destructive: true }) : true; if (!approve) return; await api('/api/portal/account/deletion-request', { password: $('#deletion-password').value }); event.target.reset(); status(t('Žádost o výmaz byla zaznamenána.', 'Deletion request recorded.')); }); });
    $('#ranking-metric')?.addEventListener('change', async event => { metric = event.target.value; try { rankings = (await api(`/api/economysuite/leaderboard?metric=${metric}`)).entries; render(); } catch (failure) { status(failure.message, true); } });
    $('#approve-pair')?.addEventListener('click', event => action(event.currentTarget, async () => { const result = await api('/api/economysuite/pair/approve', { token: pairingToken }); pairConfirmation = result.command; sessionStorage.removeItem('es-pair'); pairingToken = ''; render(); }));
  }
  $('#refresh-data').addEventListener('click', async () => {
    refreshBaseline = Number(account?.synced_at || 0); refreshStarted = Date.now(); renderConnection();
    try {
      await api('/api/economysuite/refresh', {});
      status(account?.server_status === 'disconnected' ? t('Obnovení čeká, až se server připojí.', 'Refresh is queued until the server connects.') : t('Načítám čerstvá data přímo ze serveru…', 'Loading fresh data directly from the server…'));
    } catch (failure) { refreshBaseline = null; renderConnection(); status(failure.message, true); }
  });
  async function load() {
    try { account = await api('/api/economysuite/account'); }
    catch (failure) { if (failure.status === 401 && !['store', 'pair'].includes(route)) { location.replace(`/login?product=economysuite&next=${encodeURIComponent(location.pathname)}`); return; } if (failure.status !== 401) status(failure.message, true); }
    try {
      if (route === 'store') { const catalog = await api('/api/economysuite/catalog'); packages = catalog.packages; purchasesEnabled = catalog.purchases_enabled; }
      if (route === 'purchases' && account) orders = (await api('/api/economysuite/orders')).orders;
      if (route === 'statistics' && account) rankings = (await api(`/api/economysuite/leaderboard?metric=${metric}`)).entries;
      if (route === 'pair' && account && pairingToken) pairing = await api('/api/economysuite/pair/inspect', { token: pairingToken });
    } catch (failure) { status(failure.message, true); }
    render();
  }
  $('#language').addEventListener('click', () => { lang = lang === 'cs' ? 'en' : 'cs'; localStorage.setItem('es-language', lang); render(); });
  $('#logout').addEventListener('click', () => action($('#logout'), async () => { await api('/api/portal/logout', {}); location.assign('/login?product=economysuite'); }));
  load();
  setInterval(async () => {
    if (document.hidden) return;
    try {
      const latest = await api('/api/economysuite/account'); account = latest; renderConnection();
      if (refreshBaseline !== null && Number(latest.synced_at || 0) > refreshBaseline) { refreshBaseline = null; await load(); status(t('Data byla obnovena ze serveru.', 'Data refreshed from the server.')); return; }
      if (refreshBaseline !== null && Date.now() - refreshStarted > 45000) { refreshBaseline = null; renderConnection(); status(t('Server zatím nová data neposlal. Zkus obnovení později.', 'The server has not sent fresh data yet. Try again later.'), true); }
      if (successfulOrder) { orders = (await api('/api/economysuite/orders')).orders; render(); }
    } catch { const connection = $('#connection'); connection.dataset.state = 'disconnected'; connection.innerHTML = `<span class="es-connection-dot" aria-hidden="true"></span><span>${escape(t('Server je odpojený', 'Server disconnected'))}</span>`; }
  }, 5000);
})();
