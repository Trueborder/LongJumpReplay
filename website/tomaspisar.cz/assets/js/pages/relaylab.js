(() => {
  'use strict';
  const Core = window.RelayLabCore;
  if (!Core) return;

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const feedback = window.LJR_FEEDBACK;
  const state = { swimmers: [], settings: { distance: 50, poolLength: 25, period: 'last12', dateFrom: '', dateTo: '', includeRelaySplits: false } };
  let searchTimer = 0;
  let searchController = null;
  let activeSuggestion = -1;
  let activeDialogId = null;

  const copy = {
    en: { searching: 'Searching Czech Swimming…', noMatches: 'No public swimmer matched that search.', sourceError: 'The public record could not be loaded. Try again or use an exact profile URL.', duplicate: 'Already in your squad.', loaded: 'Public results loaded', loading: 'Loading results…', official: 'Official', relay: 'Relay split', noLineup: 'Add at least four swimmers with complete matching times.', choose: 'Choose a swimmer from the suggestions or enter an exact number/profile URL.', added: 'Swimmer added.', timesLoaded: 'Official times loaded.', manualTimesLoaded: 'Manual times entered.', noTimes: 'No matching times were found.' },
    cs: { searching: 'Hledám v ČSPS…', noMatches: 'Veřejné databázi neodpovídá žádný plavec.', sourceError: 'Veřejný záznam se nepodařilo načíst. Zkuste to znovu nebo použijte přesné URL profilu.', duplicate: 'Tento plavec už v týmu je.', loaded: 'Veřejné výsledky načteny', loading: 'Načítám výsledky…', official: 'Oficiální', relay: 'Štafetový úsek', noLineup: 'Přidejte alespoň čtyři plavce s úplnými odpovídajícími časy.', choose: 'Vyberte plavce z návrhů nebo zadejte přesné číslo či URL profilu.', added: 'Plavec přidán.', timesLoaded: 'Oficiální časy načteny.', manualTimesLoaded: 'Časy zadány ručně.', noTimes: 'Nebyly nalezeny odpovídající časy.' }
  };
  const t = (key) => (copy[document.documentElement.lang === 'cs' ? 'cs' : 'en'][key] || copy.en[key] || key);
  const announce = (message) => { let live = $('#relaylab-live'); if (!live) { live = document.createElement('p'); live.id = 'relaylab-live'; live.className = 'sr-only'; live.setAttribute('aria-live', 'polite'); $('.relaylab-page')?.prepend(live); } if (live) live.textContent = message; };
  const setSearchFeedback = (message, kind = 'info') => feedback?.inline($('#search-feedback'), message, kind);
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const initials = (swimmer) => `${(swimmer.firstName || '?')[0]}${(swimmer.lastName || '?')[0]}`.toUpperCase();
  const displayName = (swimmer) => `${swimmer.firstName || ''} ${swimmer.lastName || ''}`.trim() || `ID ${swimmer.id}`;
  const formatMs = (value) => { const ms = Math.round(Number(value)); if (!Number.isFinite(ms)) return '—'; const minutes = Math.floor(ms / 60000); const seconds = ((ms % 60000) / 1000).toFixed(2).padStart(5, '0'); return `${minutes ? `${minutes}:` : ''}${seconds}`; };
  const parseTime = (value) => { const raw = String(value || '').trim().replace(',', '.'); if (!raw) return null; if (/^\d+(?:\.\d+)?$/.test(raw)) return Math.round(Number(raw) * 1000); const match = raw.match(/^(\d+):([0-5]?\d)(?:\.(\d{1,2}))?$/); if (!match) return null; return Math.round((Number(match[1]) * 60 + Number(match[2]) + Number(`0.${match[3] || '0'}`)) * 1000); };
  const parseSwimmerId = (value) => { const match = String(value || '').trim().match(/(?:\/|^)(\d{3,9})\/?$/); return match ? Number(match[1]) : null; };
  const currentSettings = () => ({ ...state.settings, dateFrom: $('#date-from')?.value || state.settings.dateFrom, dateTo: $('#date-to')?.value || state.settings.dateTo, now: new Date() });

  function setSearchLoading(loading) { $('#search-spinner')?.classList.toggle('is-loading', loading); }
  function closeSuggestions() { const list = $('#suggestions'); if (!list) return; list.hidden = true; $('#swimmer-search')?.setAttribute('aria-expanded', 'false'); activeSuggestion = -1; }
  function renderSuggestions(swimmers) {
    const list = $('#suggestions'); if (!list) return;
    list.innerHTML = '';
    if (!swimmers.length) { const li = document.createElement('li'); li.className = 'suggestion-empty'; li.textContent = t('noMatches'); list.append(li); list.hidden = false; $('#swimmer-search')?.setAttribute('aria-expanded', 'true'); return; }
    swimmers.forEach((swimmer, index) => { const li = document.createElement('li'); li.setAttribute('role', 'option'); const button = document.createElement('button'); button.type = 'button'; button.className = 'suggestion'; button.dataset.index = String(index); button.innerHTML = `<span class="suggestion-main"><span class="suggestion-name">${escape(displayName(swimmer))}</span><span class="suggestion-meta">${escape(swimmer.birthYear || '—')} · ${escape(swimmer.clubAbbrev || '—')}</span></span><span class="suggestion-id">${escape(swimmer.id)}</span>`; li.append(button); list.append(li); });
    list._items = swimmers; list.hidden = false; $('#swimmer-search')?.setAttribute('aria-expanded', 'true');
  }
  async function searchSwimmers(query) {
    searchController?.abort(); searchController = new AbortController(); setSearchLoading(true); setSearchFeedback('', 'info'); announce(t('searching'));
    try { const response = await fetch(`/api/swimming/search?q=${encodeURIComponent(query)}`, { signal: searchController.signal, headers: { accept: 'application/json' } }); const data = await response.json(); if (!response.ok) throw new Error(data.error?.code || 'search'); renderSuggestions(data.swimmers || []); }
    catch (error) { if (error.name !== 'AbortError') { renderSuggestions([]); setSearchFeedback(t('sourceError'), 'error'); announce(t('sourceError')); } }
    finally { setSearchLoading(false); }
  }

  function renderSquad() {
    const list = $('#squad-list'); if (!list) return; $('#squad-count').textContent = `${state.swimmers.length} / 16`;
    if (!state.swimmers.length) { list.innerHTML = `<div class="empty-squad" id="empty-squad"><span class="empty-mark" aria-hidden="true">+</span><p>${document.documentElement.lang === 'cs' ? 'Vaše štafeta začíná zde.' : 'Your relay starts here.'}</p><small>${document.documentElement.lang === 'cs' ? 'Vyhledejte prvního plavce výše.' : 'Search above to add the first swimmer.'}</small></div>`; return; }
    list.innerHTML = state.swimmers.map((swimmer) => `<div class="swimmer-row" data-swimmer-id="${escape(swimmer.id)}" role="button" tabindex="0" aria-label="${document.documentElement.lang === 'cs' ? 'Zobrazit časy' : 'View times'} ${escape(displayName(swimmer))}"><span class="swimmer-avatar" aria-hidden="true">${escape(initials(swimmer))}</span><span class="swimmer-copy"><strong class="swimmer-name">${escape(displayName(swimmer))}</strong><small class="swimmer-meta">${escape(swimmer.birthYear || '—')} · ${escape(swimmer.clubAbbrev || '—')}</small></span><span class="swimmer-status ${swimmer.error ? 'is-error' : ''}">${swimmer.loading ? t('loading') : swimmer.error ? '!' : swimmer.manualOnly ? (document.documentElement.lang === 'cs' ? 'Neregistrovaný' : 'Unregistered') : t('loaded')}</span><button class="remove-swimmer" type="button" data-remove-id="${escape(swimmer.id)}" aria-label="${document.documentElement.lang === 'cs' ? 'Odebrat' : 'Remove'} ${escape(displayName(swimmer))}"><svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg></button></div>`).join('');
    if (activeDialogId) { const active = state.swimmers.find((swimmer) => String(swimmer.id) === String(activeDialogId)); if (active) renderTimesDialog(active); }
  }

  function renderTimesDialog(swimmer) {
    const title = $('#swimmer-dialog-title'); const meta = $('#swimmer-dialog-meta'); const status = $('#swimmer-dialog-status'); const target = $('#swimmer-dialog-times'); const profile = $('#swimmer-dialog-profile');
    if (!title || !meta || !status || !target || !profile) return;
    title.textContent = displayName(swimmer); meta.textContent = swimmer.manualOnly ? (document.documentElement.lang === 'cs' ? 'Neregistrovaný plavec · ručně zadané časy' : 'Unregistered swimmer · manually entered times') : `${swimmer.birthYear || '—'} · ${swimmer.clubAbbrev || '—'} · ID ${swimmer.id}`;
    if (swimmer.manualOnly) { profile.hidden = true; profile.removeAttribute('href'); } else { profile.hidden = false; profile.href = swimmer.profileUrl || `https://vysledky.czechswimming.cz/lide/${swimmer.id}`; }
    if (swimmer.error) status.textContent = swimmer.error; else if (swimmer.loading) status.textContent = t('loading'); else if (swimmer.manualOnly) status.textContent = t('manualTimesLoaded'); else status.textContent = swimmer.performances?.length ? `${t('timesLoaded')} ${swimmer.performances.length}` : t('noTimes');
    const settings = currentSettings();
    target.innerHTML = Core.STROKES.map((stroke) => { const manual = swimmer.manualTimes?.[stroke.key]; const selected = manual ? { timeMs: manual, source: 'manual' } : Core.selectBestPerformance(swimmer.performances || [], stroke.key, settings); return `<tr><th scope="row">${escape(document.documentElement.lang === 'cs' ? stroke.labelCs : stroke.label)}</th><td>${selected ? formatMs(selected.timeMs) : '—'}</td><td>${selected?.date ? escape(selected.date.slice(0, 10)) : selected?.source === 'manual' ? (document.documentElement.lang === 'cs' ? 'Ručně' : 'Manual') : '—'}</td><td>${selected?.poolLength ? `${escape(selected.poolLength)} m` : selected?.source === 'manual' ? '—' : '—'}</td><td>${escape(selected?.venue || '—')}</td></tr>`; }).join('');
  }
  function openSwimmerDialog(swimmer) { const dialog = $('#swimmer-dialog'); if (!dialog) return; activeDialogId = swimmer.id; renderTimesDialog(swimmer); if (typeof dialog.showModal === 'function' && !dialog.open) dialog.showModal(); else dialog.hidden = false; }
  function closeSwimmerDialog() { const dialog = $('#swimmer-dialog'); activeDialogId = null; if (dialog?.open) dialog.close(); else if (dialog) dialog.hidden = true; }

  async function loadSwimmer(swimmer) {
    swimmer.loading = true; renderSquad();
    try { const response = await fetch(`/api/swimming/swimmers/${encodeURIComponent(swimmer.id)}/times`, { headers: { accept: 'application/json' } }); const data = await response.json(); if (!response.ok) throw new Error(data.error?.code || 'profile'); Object.assign(swimmer, data.swimmer, { performances: data.performances || [], fetchedAt: data.fetchedAt, loading: false, error: '' }); announce(`${displayName(swimmer)} — ${t('loaded')}`); }
    catch (_) { swimmer.loading = false; swimmer.error = t('sourceError'); announce(swimmer.error); }
    swimmer.clubAbbrev = swimmer.clubAbbrev || swimmer.clubName || '';
    renderSquad();
  }
  function addSwimmer(record) {
    if (state.swimmers.some((item) => String(item.id) === String(record.id))) { setSearchFeedback(t('duplicate'), 'warning'); announce(t('duplicate')); closeSuggestions(); return; }
    if (state.swimmers.length >= 16) { setSearchFeedback(document.documentElement.lang === 'cs' ? 'Tým už obsahuje maximálně 16 plavců.' : 'A relay can contain at most 16 swimmers.', 'warning'); return; }
    const swimmer = { id: record.id, firstName: record.firstName || '', lastName: record.lastName || '', birthYear: record.birthYear || null, clubAbbrev: record.clubAbbrev || '', profileUrl: record.profileUrl || `https://vysledky.czechswimming.cz/lide/${record.id}`, performances: [], loading: true, error: '' };
    state.swimmers.push(swimmer); renderSquad(); closeSuggestions(); $('#swimmer-search').value = ''; setSearchFeedback('', 'info'); feedback?.toast.success(t('added'), { title: document.documentElement.lang === 'cs' ? 'Přidáno' : 'Swimmer added' }); announce(t('added')); loadSwimmer(swimmer);
  }
  function closeUnregisteredDialog() { const dialog = $('#unregistered-dialog'); if (dialog?.open) dialog.close(); else if (dialog) dialog.hidden = true; }
  function addUnregisteredSwimmer(event) {
    event.preventDefault();
    const form = $('#unregistered-form'); const error = $('#unregistered-error'); if (!form || !error) return;
    const name = $('#unregistered-name').value.trim(); const values = {};
    Core.STROKES.forEach((stroke) => { values[stroke.key] = parseTime(form.elements[stroke.key].value); });
    if (!name || Object.values(values).some((value) => !Number.isFinite(value) || value <= 0)) { error.textContent = document.documentElement.lang === 'cs' ? 'Zadejte jméno a všechny čtyři časy ve formátu m:ss.cc.' : 'Enter a name and all four times in m:ss.cc format.'; error.hidden = false; return; }
    const parts = name.split(/\s+/); const swimmer = { id: `unregistered-${Date.now()}`, firstName: parts.slice(0, -1).join(' ') || parts[0], lastName: parts.length > 1 ? parts[parts.length - 1] : '', birthYear: null, clubAbbrev: '', profileUrl: '', performances: [], manualOnly: true, manualTimes: values, loading: false, error: '' };
    state.swimmers.push(swimmer); renderSquad(); form.reset(); error.hidden = true; closeUnregisteredDialog(); announce(t('added')); openSwimmerDialog(swimmer);
  }

  function renderResults(outcome) {
    const section = $('#results'); if (!section) return; section.hidden = false; $('#best-total').textContent = outcome.results[0] ? formatMs(outcome.results[0].totalMs) : '—';
    const best = outcome.results[0]; if (!best) { $('#best-lineup').innerHTML = `<div class="evidence-placeholder"><p>${t('noLineup')}</p></div>`; $('#alternatives').innerHTML = ''; return; }
    $('#best-lineup').innerHTML = best.legs.map((leg, index) => `<article class="leg-card"><span class="leg-number">0${index + 1} / ${escape(document.documentElement.lang === 'cs' ? leg.stroke.labelCs : leg.stroke.label).toUpperCase()}</span><h3>${escape(displayName(leg.swimmer))}</h3><p class="leg-swimmer">${escape(leg.swimmer.clubAbbrev || '—')} · ${escape(leg.swimmer.birthYear || '—')}</p><div class="leg-time">${formatMs(leg.performance.timeMs)}</div><div class="leg-source">${escape(leg.performance.source === 'manual' ? 'Manual' : leg.performance.relayPart ? t('relay') : t('official'))}</div></article>`).join('');
    const alternatives = outcome.results.slice(1); $('#alternatives').innerHTML = alternatives.length ? `<p class="relaylab-kicker">${document.documentElement.lang === 'cs' ? 'DALŠÍ MOŽNOSTI' : 'NEXT BEST OPTIONS'}</p>${alternatives.map((result, index) => `<div class="alternative"><strong>${document.documentElement.lang === 'cs' ? `Varianta ${index + 2}` : `Option ${index + 2}`} · ${result.legs.map((leg) => escape(leg.swimmer.lastName || leg.swimmer.firstName)).join(' / ')}</strong><span>${formatMs(result.totalMs)}</span><small>+${formatMs(result.totalMs - best.totalMs)}</small></div>`).join('')}` : '';
    const warning = $('#result-warning'); warning.hidden = !state.settings.includeRelaySplits; warning.textContent = document.documentElement.lang === 'cs' ? 'Štafetové úseky jsou použity tak, jak byly zaznamenány. U úseků mimo znak může být započten letmý start.' : 'Relay splits are used as recorded. Non-backstroke legs may include a flying start.';
    section.scrollIntoView({ behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
  }
  function calculate() { const settings = currentSettings(); state.settings = { ...state.settings, ...settings }; const manualTimes = Object.fromEntries(state.swimmers.filter((swimmer) => swimmer.manualOnly && swimmer.manualTimes).map((swimmer) => [swimmer.id, swimmer.manualTimes])); const outcome = Core.optimize(state.swimmers, { ...settings, manualTimes }); renderResults(outcome); if (!outcome.results.length) announce(t('noLineup')); else announce(`${document.documentElement.lang === 'cs' ? 'Nejlepší sestava' : 'Best lineup'} ${formatMs(outcome.results[0].totalMs)}`); }
  function syncPoolOptions() { const distance = Number(document.querySelector('input[name="distance"]:checked')?.value || 50); const pool50 = document.querySelector('input[name="pool"][value="50"]'); const pool25 = document.querySelector('input[name="pool"][value="25"]'); if (!pool50 || !pool25) return; pool50.disabled = distance === 25; if (distance === 25 && pool50.checked) { pool50.checked = false; pool25.checked = true; state.settings.poolLength = 25; } }

  $('#swimmer-search')?.addEventListener('input', (event) => { const query = event.target.value.trim(); closeSuggestions(); clearTimeout(searchTimer); if (parseSwimmerId(query) || query.length < 2) return; searchTimer = setTimeout(() => searchSwimmers(query), 260); });
  $('#swimmer-search')?.addEventListener('keydown', (event) => { const list = $('#suggestions'); const items = list?._items || []; if (event.key === 'ArrowDown' && items.length) { event.preventDefault(); activeSuggestion = Math.min(activeSuggestion + 1, items.length - 1); $$('.suggestion').forEach((item, index) => item.parentElement.setAttribute('aria-selected', String(index === activeSuggestion))); } else if (event.key === 'ArrowUp' && items.length) { event.preventDefault(); activeSuggestion = Math.max(activeSuggestion - 1, 0); } else if (event.key === 'Enter') { event.preventDefault(); if (activeSuggestion >= 0 && items[activeSuggestion]) addSwimmer(items[activeSuggestion]); else { const id = parseSwimmerId(event.target.value); if (id) addSwimmer({ id, profileUrl: `https://vysledky.czechswimming.cz/lide/${id}` }); else announce(t('choose')); } } else if (event.key === 'Escape') closeSuggestions(); });
  $('#suggestions')?.addEventListener('click', (event) => { const button = event.target.closest('.suggestion'); if (button) addSwimmer($('#suggestions')._items[Number(button.dataset.index)]); });
  $('#squad-list')?.addEventListener('click', (event) => { const remove = event.target.closest('[data-remove-id]'); if (remove) { state.swimmers = state.swimmers.filter((swimmer) => String(swimmer.id) !== String(remove.dataset.removeId)); renderSquad(); return; } const row = event.target.closest('[data-swimmer-id]'); if (row) { const swimmer = state.swimmers.find((item) => String(item.id) === String(row.dataset.swimmerId)); if (swimmer) openSwimmerDialog(swimmer); } });
  $('#squad-list')?.addEventListener('keydown', (event) => { if (!['Enter', ' '].includes(event.key) || event.target.closest('[data-remove-id]')) return; const row = event.target.closest('[data-swimmer-id]'); if (!row) return; event.preventDefault(); const swimmer = state.swimmers.find((item) => String(item.id) === String(row.dataset.swimmerId)); if (swimmer) openSwimmerDialog(swimmer); });
  $('#close-swimmer-dialog')?.addEventListener('click', closeSwimmerDialog); $('#swimmer-dialog')?.addEventListener('cancel', (event) => { event.preventDefault(); closeSwimmerDialog(); }); $('#swimmer-dialog')?.addEventListener('click', (event) => { if (event.target === event.currentTarget) closeSwimmerDialog(); });
  $('#open-unregistered')?.addEventListener('click', () => { const dialog = $('#unregistered-dialog'); if (dialog && typeof dialog.showModal === 'function') dialog.showModal(); else if (dialog) dialog.hidden = false; $('#unregistered-name')?.focus(); }); $('#close-unregistered')?.addEventListener('click', closeUnregisteredDialog); $('#unregistered-dialog')?.addEventListener('cancel', (event) => { event.preventDefault(); closeUnregisteredDialog(); }); $('#unregistered-dialog')?.addEventListener('click', (event) => { if (event.target === event.currentTarget) closeUnregisteredDialog(); }); $('#unregistered-form')?.addEventListener('submit', addUnregisteredSwimmer);
  $$('input[name="distance"], input[name="pool"]').forEach((input) => input.addEventListener('change', () => { syncPoolOptions(); state.settings.distance = Number(document.querySelector('input[name="distance"]:checked').value); state.settings.poolLength = Number(document.querySelector('input[name="pool"]:checked').value); if (activeDialogId) { const swimmer = state.swimmers.find((item) => String(item.id) === String(activeDialogId)); if (swimmer) renderTimesDialog(swimmer); } }));
  $('#period')?.addEventListener('change', (event) => { state.settings.period = event.target.value; $('#custom-dates').hidden = event.target.value !== 'custom'; if (activeDialogId) { const swimmer = state.swimmers.find((item) => String(item.id) === String(activeDialogId)); if (swimmer) renderTimesDialog(swimmer); } });
  $('#date-from')?.addEventListener('change', () => { if (activeDialogId) { const swimmer = state.swimmers.find((item) => String(item.id) === String(activeDialogId)); if (swimmer) renderTimesDialog(swimmer); } }); $('#date-to')?.addEventListener('change', () => { if (activeDialogId) { const swimmer = state.swimmers.find((item) => String(item.id) === String(activeDialogId)); if (swimmer) renderTimesDialog(swimmer); } }); $('#include-relay')?.addEventListener('change', (event) => { state.settings.includeRelaySplits = event.target.checked; if (activeDialogId) { const swimmer = state.swimmers.find((item) => String(item.id) === String(activeDialogId)); if (swimmer) renderTimesDialog(swimmer); } }); $('#calculate')?.addEventListener('click', calculate);
  document.addEventListener('click', (event) => { if (!event.target.closest('.search-wrap')) closeSuggestions(); });
  new MutationObserver(() => { renderSquad(); if (activeDialogId) { const swimmer = state.swimmers.find((item) => String(item.id) === String(activeDialogId)); if (swimmer) renderTimesDialog(swimmer); } }).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
  syncPoolOptions(); renderSquad();
})();
