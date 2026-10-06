const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..', 'tomaspisar.cz');
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8');
const sharedScript = read('assets/js/components/site.js');
const accountScript = read('assets/js/account/account.js');
const contactScript = read('assets/js/pages/contact.js');
const relayScript = read('assets/js/pages/relaylab.js');
const componentsCss = read('assets/css/components.css');

test('shared feedback primitives cover toast, inline, and modal decisions', () => {
  assert.match(sharedScript, /window.LJR_FEEDBACK = feedback/);
  assert.match(sharedScript, /toast: { success:/);
  assert.match(sharedScript, /const promiseToast =/);
  assert.match(sharedScript, /const setBusy =/);
  assert.match(sharedScript, /const setInline =/);
  assert.match(sharedScript, /const confirm =/);
  assert.match(sharedScript, /beforetoggle/);
  assert.match(componentsCss, /.toast-region/);
  assert.match(componentsCss, /.feedback-modal/);
  assert.match(componentsCss, /.inline-message/);
  assert.match(componentsCss, /aria-busy="true"/);
});

test('both account dashboards expose loading, retry, and refresh feedback states', () => {
  const economyHtml = read('account/economysuite/index.html');
  const economyScript = read('account/economysuite/app.js');
  const dashboardHtml = read('account/dashboard/index.html');
  const dashboardScript = read('assets/js/account/account.js');
  const dashboardCss = read('assets/css/pages/account.css');
  assert.match(economyHtml, /assets\/js\/components\/site\.js/);
  assert.match(economyHtml, /es-skeleton-grid/);
  assert.match(economyScript, /const loadError =/);
  assert.match(economyScript, /retry-load/);
  assert.match(economyScript, /feedback\?\.promise/);
  assert.match(dashboardHtml, /id="dashboard-refresh"/);
  assert.match(dashboardHtml, /dashboard-skeleton/);
  assert.match(dashboardScript, /setDashboardRetry/);
  assert.match(dashboardCss, /dashboard-skeleton/);
});

test('destructive account actions use the reusable modal and successes use toasts', () => {
  assert.doesNotMatch(accountScript, /window\.confirm\s*\(/);
  assert.match(accountScript, /feedback\?\.confirm/);
  assert.match(accountScript, /notify\('success'/);
  assert.match(accountScript, /readableError/);
});

test('form and RelayLab feedback stays contextual', () => {
  assert.match(contactScript, /feedback\?\.inline/);
  assert.match(contactScript, /toast.success/);
  assert.match(relayScript, /setSearchFeedback/);
  assert.match(relayScript, /toast.success/);
});

test('website scripts contain no browser alert or confirm calls', () => {
  const scripts = [
    ...fs.globSync(path.join(root, '**', '*.js'), { exclude: (file) => file.includes('node_modules') })
  ].map((file) => fs.readFileSync(file, 'utf8')).join('\n');
  assert.doesNotMatch(scripts, /\b(?:window\.)?(?:alert|confirm)\s*\(/);
});
