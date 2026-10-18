const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(path.join(__dirname, '../tomaspisar.cz/account/economysuite/app.js'), 'utf8');
const flush = () => new Promise(setImmediate);

function harness(options = {}) {
  const optionsForFailure = options.failCosmetic;
  const rankDetails = options.rankDetails;
  const nodes = new Map();
  const classes = () => ({ add() {}, remove() {}, toggle() {} });
  for (const key of ['#navigation-dialog', '#menu-toggle', '.es-sidebar', '.es-layout', '#mobile-navigation-content', '#close-navigation', '#language', '#logout', '#support', '#navigation-title', '#navigation', '#page-title', '#page-description', '#player-identity', '#connection', '.es-live-actions', '#refresh-data', '#content', '#navigation [aria-current="page"]']) {
    const node = { dataset: {}, attributes: {}, handlers: {}, classList: classes(), disabled: false, isConnected: true, open: false,
      addEventListener(name, listener) { this.handlers[name] = listener; },
      setAttribute(name, value) { this.attributes[name] = value; },
      removeAttribute(name) { delete this.attributes[name]; },
      append(child) { child.parent = this; }, prepend(child) { child.parent = this; },
      focus() { this.focused = true; },
      closest() { return nodes.get('.es-live-actions'); },
      showModal() { this.open = true; },
      close() { this.open = false; this.handlers.close?.(); }
    };
    nodes.set(key, node);
  }
  const rankButtons = [];
  if (options.rankDetails) {
    const makeNode = () => ({handlers:{},dataset:{},classList:classes(),hidden:true,open:false,isConnected:true,addEventListener(name,fn){this.handlers[name]=fn;},focus(){this.focused=true;},showModal(){this.open=true;},close(){this.open=false;this.handlers.close?.();}});
    for (const key of ['#rank-details-dialog','#rank-details-content','#close-rank-details','#order-rank','#purchase-dialog','#purchase-dialog-summary','#purchase-consent-form','#confirm-purchase','#close-purchase-dialog','#cancel-purchase']) nodes.set(key,makeNode());
    nodes.get('#purchase-consent-form').reset = () => { nodes.get('#purchase-consent-form').wasReset=true; };
    nodes.get('#order-rank').dataset.price='price_mvp';
    const card=makeNode();card.dataset.rank='mvp';rankButtons.push(card);
  }
  const media = { matches: true, addEventListener(name, listener) { this.change = listener; } };
  for (const key of ['#language-label', '#account-link']) nodes.set(key, {
    attributes: {}, setAttribute(name, value) { this.attributes[name] = value; }
  });
  if (options.appearance) {
    const button = { disabled: false, isConnected: true, attributes: {},
      setAttribute(name, value) { this.attributes[name] = value; }, removeAttribute(name) { delete this.attributes[name]; } };
    nodes.set('#appearance-form', { handlers: {}, elements: { prefix: { value: 'vip' }, color: { value: 'green' }, aura: { value: 'heart-vortex' }, hat: { value: 'flower' } },
      addEventListener(name, listener) { this.handlers[name] = listener; }, querySelector: () => button });
  }
  const notices = [];
  const calls = [];
  let interval, clock = 100000;
  const documentHandlers = {}, documentElement = { dataset: {} };
  const account = { link: { uuid: 'test-player', name: 'TestPlayer' }, snapshot: {}, synced_at: 10, server_status: 'connected', refresh_operation: null };
  if(options.rank) {account.snapshot.rank=options.rank;nodes.set('.es-rank-section',{outerHTML:''});}
  if(options.daily) {
    account.daily_reward={day:'2026-10-17',available:true,amount:null,status:'available',next_reset_at:1792274400};
    nodes.set('#web-daily-reward',{outerHTML:''});
    nodes.set('#claim-web-daily',{disabled:false,isConnected:true,handlers:{},attributes:{},addEventListener(name,handler){this.handlers[name]=handler;},setAttribute(name,value){this.attributes[name]=value;},removeAttribute(name){delete this.attributes[name];}});
  }
  const feedback = {
    toast: Object.fromEntries(['info', 'error', 'success', 'warning'].map(kind => [kind, message => notices.push({ kind, message })])),
    busy(button, busy) { button.disabled = busy; if (busy) button.setAttribute('aria-busy', 'true'); else button.removeAttribute('aria-busy'); },
    async promise(work, options) {
      const notice = { kind: 'info', message: options.loading }; notices.push(notice);
      try { const result = await work; Object.assign(notice, { kind: 'success', message: options.success }); return result; }
      catch (error) { Object.assign(notice, { kind: 'error', message: options.error(error) }); throw error; }
    }
  };
  vm.runInNewContext(script, {
    document: { addEventListener: (name, listener) => { documentHandlers[name] = listener; }, querySelector: key => nodes.get(key) || null, querySelectorAll: selector => selector === '[data-rank]' ? rankButtons : [], body: { classList: classes() }, documentElement, cookie: '', hidden: false },
    window: { LJR_FEEDBACK: feedback }, matchMedia: () => media,
    localStorage: { getItem: () => null, setItem() {} }, sessionStorage: { getItem: () => null, removeItem() {}, setItem() {} },
    location: { pathname: '/economysuite/'+(options.route||'store'), search: '', hash: '', replace() {}, assign() {} },
    URLSearchParams, Intl, Date: class extends Date { static now() { return clock; } },
    setInterval: callback => { interval = callback; },
    fetch: async (url, options) => {
      calls.push({ url, method: options.method, body: options.body ? JSON.parse(options.body) : undefined });
      if(url.endsWith('/daily/claim')) {await flush();return {ok:true,json:async()=>({daily_reward:{...account.daily_reward,available:false,amount:4,status:'pending'}})};}
      if (url.endsWith('/cosmetics') && calls.at(-1).body.type === optionsForFailure) return { ok: false, status: 503, json: async () => ({ error: 'unavailable' }) };
      const data = url.endsWith('/account') ? account : url.endsWith('/refresh') ? { operation_id: 'refresh-1' } : { packages: rankDetails ? [{id:'price_mvp',rank_id:'mvp',name:'MVP',currency:'rank',price_minor:9900,checkoutable:true}] : [], purchases_enabled: true };
      return { ok: true, json: async () => data };
    }
  });
  return { nodes, rankButtons, media, notices, calls, account, documentHandlers, documentElement, tick: () => interval(), advance: ms => { clock += ms; } };
}

test('daily reward appears in both store and overview and double-click cannot submit twice',async()=>{
  for(const route of ['store','overview']){
    const h=harness({daily:true,route});await flush();
    assert.match(h.nodes.get('#content').innerHTML,/Denní webová odměna/);
    assert.match(h.nodes.get('#content').innerHTML,/Vyzvednout 1–5 tokenů zdarma/);
    const button=h.nodes.get('#claim-web-daily');
    button.handlers.click({currentTarget:button});button.handlers.click({currentTarget:button});
    await flush();await flush();
    assert.equal(h.calls.filter(call=>call.url.endsWith('/daily/claim')).length,1);
    assert.equal(h.account.daily_reward.amount,4);
    assert.match(h.nodes.get('#web-daily-reward').outerHTML,/Odměna čeká na server/);
  }
});
test('expired rank snapshots do not pretend the rank and its profile frame are still active',async()=>{
  const h=harness({route:'appearance',rank:{id:'mvp',expires_at:99999,frame:3,remaining_ms:{}}});await flush();
  assert.match(h.nodes.get('#content').innerHTML,/Čeká na synchronizaci/);
  assert.match(h.nodes.get('#content').innerHTML,/es-rank-frame-0/);
  assert.doesNotMatch(h.nodes.get('#content').innerHTML,/es-rank-frame-3/);
});
test('rank expiry refreshes its own panel while leaving appearance forms untouched',async()=>{
  const h=harness({route:'appearance',appearance:true,rank:{id:'mvp',expires_at:100010,frame:3,remaining_ms:{}}});await flush();
  const form=h.nodes.get('#appearance-form');h.advance(20);await h.tick();
  assert.match(h.nodes.get('.es-rank-section').outerHTML,/Čeká na synchronizaci/);
  assert.equal(h.nodes.get('#appearance-form'),form);
});

test('motion input follows keyboard and pointer without delaying navigation', async () => {
  const h = harness(); await flush();
  h.documentHandlers.keydown();
  assert.equal(h.documentElement.dataset.motionInput, 'keyboard');
  h.nodes.get('#menu-toggle').handlers.click();
  assert.equal(h.nodes.get('#navigation-dialog').open, true);
  h.documentHandlers.pointerdown();
  assert.equal(h.documentElement.dataset.motionInput, 'pointer');
  h.nodes.get('#close-navigation').handlers.click();
  assert.equal(h.nodes.get('#navigation-dialog').open, false);
});

test('mobile drawer restores focus and moves the same navigation back on desktop', async () => {
  const h = harness(); await flush();
  assert.equal(h.nodes.get('.es-sidebar').parent, h.nodes.get('#mobile-navigation-content'));
  h.nodes.get('#menu-toggle').handlers.click();
  assert.equal(h.nodes.get('#navigation-dialog').open, true);
  assert.equal(h.nodes.get('#menu-toggle').attributes['aria-expanded'], 'true');
  h.nodes.get('#close-navigation').handlers.click();
  assert.equal(h.nodes.get('#menu-toggle').attributes['aria-expanded'], 'false');
  assert.equal(h.nodes.get('#menu-toggle').focused, true);
  h.media.matches = false; h.media.change();
  assert.equal(h.nodes.get('.es-sidebar').parent, h.nodes.get('.es-layout'));
});

test('refresh updates one toast only after the matching operation completes', async () => {
  const h = harness(); await flush();
  const pending = h.nodes.get('#refresh-data').handlers.click(); await flush();
  await h.nodes.get('#refresh-data').handlers.click();
  assert.equal(h.calls.filter(call => call.url.endsWith('/refresh')).length, 1);
  assert.equal(h.notices.length, 1);
  assert.equal(h.nodes.get('#connection').dataset.state, 'connecting');
  h.account.synced_at = 20; // An unrelated snapshot must not complete this refresh.
  await h.tick();
  assert.equal(h.notices[0].kind, 'info');
  h.account.refresh_operation = { id: 'refresh-1', state: 'complete' };
  await h.tick(); await pending;
  assert.equal(h.notices.length, 1);
  assert.equal(h.notices[0].kind, 'success');
  assert.equal(h.nodes.get('#connection').dataset.state, 'connected');
  assert.equal(h.nodes.get('#refresh-data').disabled, false);
  assert.equal(h.nodes.get('#refresh-data').attributes['aria-busy'], undefined);
});

test('relocated language control still translates account access and survives drawer resizing', async () => {
  const h = harness(); await flush();
  const language = h.nodes.get('#language');
  assert.equal(h.nodes.get('#language-label').textContent, 'Jazyk');
  assert.equal(h.nodes.get('#account-link').attributes['aria-label'], 'Nastavení účtu');
  language.handlers.click();
  assert.equal(h.nodes.get('#language-label').textContent, 'Language');
  assert.equal(language.attributes['aria-label'], 'Switch to Czech');
  assert.equal(h.nodes.get('#account-link').title, 'Account settings');
  assert.equal(h.nodes.get('#logout').textContent, 'Sign out');
  h.media.matches = false; h.media.change();
  h.media.matches = true; h.media.change();
  assert.equal(h.nodes.get('#language'), language);
  language.handlers.click();
  assert.equal(h.nodes.get('#language-label').textContent, 'Jazyk');
});

test('refresh timeout becomes an error toast and permits another attempt', async () => {
  const h = harness(); await flush();
  const pending = h.nodes.get('#refresh-data').handlers.click(); await flush();
  h.advance(46000); await h.tick(); await pending;
  assert.equal(h.notices.length, 1);
  assert.equal(h.notices[0].kind, 'error');
  assert.equal(h.nodes.get('#refresh-data').disabled, false);
});

test('appearance snapshots all selections before currentTarget is cleared and blocks duplicate submits', async () => {
  const h = harness({ appearance: true }); await flush();
  const form = h.nodes.get('#appearance-form'), button = form.querySelector('button');
  const event = { currentTarget: form, preventDefault() {} };
  form.handlers.submit(event);
  form.handlers.submit(event); // The first submission has already disabled the button.
  event.currentTarget = null; // Native event dispatch clears this before the next await resumes.
  form.elements.color.value = 'red'; form.elements.aura.value = 'changed-by-poll';
  await flush(); await flush();
  assert.deepEqual(h.calls.filter(call => call.url.endsWith('/cosmetics')).map(call => call.body), [
    { type: 'prefix', id: 'vip' }, { type: 'color', id: 'green' }, { type: 'aura', id: 'heart-vortex' }, { type: 'hat', id: 'flower' }
  ]);
  assert.equal(button.disabled, false);
  assert.equal(h.notices.length, 1);
  assert.match(h.notices[0].message, /Vzhled čeká na potvrzení serverem/);
});

test('appearance API failure restores the button and never claims the whole appearance was queued', async () => {
  const h = harness({ appearance: true, failCosmetic: 'color' }); await flush();
  const form = h.nodes.get('#appearance-form'), event = { currentTarget: form, preventDefault() {} };
  form.handlers.submit(event); event.currentTarget = null;
  await flush(); await flush();
  assert.equal(h.calls.filter(call => call.url.endsWith('/cosmetics')).length, 2);
  assert.equal(form.querySelector('button').disabled, false);
  assert.equal(h.notices.length, 1); assert.equal(h.notices[0].kind, 'error');
});

test('rank card opens details on initial render and order moves to existing unchecked consent without payment', async () => {
  const h=harness({route:'rank',rankDetails:true}); await flush();
  h.rankButtons[0].handlers.click();
  assert.equal(h.nodes.get('#rank-details-dialog').open,true);
  assert.match(h.nodes.get('#rank-details-content').innerHTML,/Pantheon aura/);
  assert.equal(h.calls.filter(call=>call.method==='POST').length,0);
  h.nodes.get('#order-rank').handlers.click({currentTarget:h.nodes.get('#order-rank')});
  assert.equal(h.nodes.get('#rank-details-dialog').open,false);
  assert.equal(h.nodes.get('#purchase-dialog').hidden,false);
  assert.equal(h.nodes.get('#purchase-consent-form').wasReset,true);
  assert.match(h.nodes.get('#purchase-dialog-summary').innerHTML,/MVP/);
  assert.equal(h.calls.filter(call=>call.method==='POST').length,0);
  h.nodes.get('#cancel-purchase').handlers.click();
  assert.equal(h.rankButtons[0].focused,true);
});
