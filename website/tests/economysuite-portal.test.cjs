const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..', 'tomaspisar.cz', 'account', 'economysuite');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'app.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'app.css'), 'utf8');

test('EconomySuite portal exposes live server state and full data refresh', () => {
  assert.match(html, /id="connection"[^>]*data-state="connecting"/);
  assert.match(html, /id="refresh-data"/);
  assert.match(script, /server_status/);
  assert.match(script, /\/api\/economysuite\/refresh/);
  assert.match(script, /Data refreshed from the server/);
  assert.match(css, /\.es-connection\[data-state=connected\]/);
  assert.match(css, /\.es-connection\[data-state=connecting\]/);
  assert.match(css, /\.es-connection\[data-state=disconnected\]/);
  assert.match(css, /@keyframes es-connection-pulse/);
});

test('purchase return renders instructions and Minecraft currency icons', () => {
  assert.match(script, /Thank you for your purchase/);
  assert.match(script, /Check your balance with \/money or \/tokens/);
  assert.match(script, /es-amethyst/);
  assert.match(script, /es-sunflower/);
  assert.match(script, /es-order-item/);
  assert.match(script, /icon\('store'\)/);
  assert.match(script, /icon\(key\)/);
});

test('store explains how purchases support the developer', () => {
  assert.match(script, /es-support-note/);
  assert.match(script, /Novaryn Solutions/);
  assert.match(script, /All money from this store goes directly to developer/);
  assert.match(css, /\.es-support-note/);
});
