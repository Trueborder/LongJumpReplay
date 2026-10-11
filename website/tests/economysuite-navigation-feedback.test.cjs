const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(path.join(__dirname, '../tomaspisar.cz/account/economysuite/app.js'), 'utf8');
const flush = () => new Promise(setImmediate);

function harness() {
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
  const media = { matches: true, addEventListener(name, listener) { this.change = listener; } };
  const notices = [];
  const calls = [];
  let interval, clock = 100000;
  const account = { link: { uuid: 'test-player', name: 'TestPlayer' }, snapshot: {}, synced_at: 10, server_status: 'connected', refresh_operation: null };
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
    document: { querySelector: key => nodes.get(key) || null, querySelectorAll: () => [], body: { classList: classes() }, documentElement: {}, cookie: '', hidden: false },
    window: { LJR_FEEDBACK: feedback }, matchMedia: () => media,
    localStorage: { getItem: () => null, setItem() {} }, sessionStorage: { getItem: () => null, removeItem() {}, setItem() {} },
    location: { pathname: '/economysuite/store', search: '', hash: '', replace() {}, assign() {} },
    URLSearchParams, Intl, Date: class extends Date { static now() { return clock; } },
    setInterval: callback => { interval = callback; },
    fetch: async (url, options) => {
      calls.push({ url, method: options.method });
      const data = url.endsWith('/account') ? account : url.endsWith('/refresh') ? { operation_id: 'refresh-1' } : { packages: [], purchases_enabled: true };
      return { ok: true, json: async () => data };
    }
  });
  return { nodes, media, notices, calls, account, tick: () => interval(), advance: ms => { clock += ms; } };
}

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

test('refresh timeout becomes an error toast and permits another attempt', async () => {
  const h = harness(); await flush();
  const pending = h.nodes.get('#refresh-data').handlers.click(); await flush();
  h.advance(46000); await h.tick(); await pending;
  assert.equal(h.notices.length, 1);
  assert.equal(h.notices[0].kind, 'error');
  assert.equal(h.nodes.get('#refresh-data').disabled, false);
});
