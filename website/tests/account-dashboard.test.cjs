const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const accountRoot = path.join(__dirname, '..', 'tomaspisar.cz', 'account');
const html = fs.readFileSync(path.join(accountRoot, 'dashboard', 'index.html'), 'utf8');
const css = fs.readFileSync(path.join(accountRoot, 'account.css'), 'utf8');
const script = fs.readFileSync(path.join(accountRoot, 'account.js'), 'utf8');
const categories = ['overview', 'licence', 'activation-key', 'devices', 'billing', 'help'];

test('dashboard categories have distinct deep links and routed content', () => {
  for (const category of categories) {
    assert.match(html, new RegExp(`href="/dashboard/${category}"`));
    assert.match(html, new RegExp(`data-dashboard-route="${category}"`));
  }
  assert.doesNotMatch(html, /class="dashboard-nav"[\s\S]*?href="#/);
  assert.match(script, /dashboardRoutes = new Set\(\['overview', 'licence', 'activation-key', 'devices', 'billing', 'help'\]\)/);
});

test('device controls keep actions together and use a dedicated SVG close icon', () => {
  assert.match(css, /\.row-actions \{[^}]*flex-wrap: nowrap;/);
  assert.match(css, /\.device-table th:last-child, \.device-table td:last-child \{[^}]*min-width: 210px;/);
  assert.match(html, /id="device-details-close" class="dialog-close-button"[\s\S]*?<svg/);
  assert.doesNotMatch(html, /id="device-details-close" class="icon-button"/);
});

test('activation key can be copied while the displayed value stays hidden', () => {
  assert.match(html, /id="activation-key-copy" class="button button-outline" type="button"/);
  assert.doesNotMatch(html, /id="activation-key-copy"[^>]*disabled/);
  assert.match(script, /const copyActivationKey = async \(\) =>/);
  assert.match(script, /value = data\.key;[\s\S]*?writeClipboard\(value\)/);
  assert.match(script, /Key copied without revealing it\./);
});

test('dashboard markup does not contain duplicate ids', () => {
  const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map((match) => match[1]);
  assert.equal(new Set(ids).size, ids.length);
});
