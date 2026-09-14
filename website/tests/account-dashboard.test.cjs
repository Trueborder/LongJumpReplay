const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const accountRoot = path.join(__dirname, '..', 'tomaspisar.cz', 'account');
const assetsRoot = path.join(__dirname, '..', 'tomaspisar.cz', 'assets');
const html = fs.readFileSync(path.join(accountRoot, 'dashboard', 'index.html'), 'utf8');
const pairingHtml = fs.readFileSync(path.join(accountRoot, 'approve', 'pairing', 'index.html'), 'utf8');
const css = fs.readFileSync(path.join(assetsRoot, 'css', 'pages', 'account.css'), 'utf8');
const script = fs.readFileSync(path.join(assetsRoot, 'js', 'account', 'account.js'), 'utf8');
const pairingScript = fs.readFileSync(path.join(assetsRoot, 'js', 'account', 'pairing-approval.js'), 'utf8');
const categories = ['overview', 'licence', 'activation-key', 'activation', 'devices', 'billing', 'profile', 'help'];

test('dashboard categories have distinct deep links and routed content', () => {
  for (const category of categories) {
    assert.match(html, new RegExp(`href="/dashboard/${category}"`));
    assert.match(html, new RegExp(`data-dashboard-route="${category}"`));
  }
  assert.doesNotMatch(html, /class="dashboard-nav"[\s\S]*?href="#/);
  assert.match(script, /dashboardRoutes = new Set\(\['overview', 'licence', 'activation-key', 'activation', 'devices', 'billing', 'profile', 'help'\]\)/);
});

test('profile category edits identity and password through existing account APIs', () => {
  assert.match(html, /id="profile-form"/);
  assert.match(html, /id="password-enroll-form"/);
  assert.match(script, /\/api\/portal\/profile/);
  assert.match(script, /\/api\/portal\/password\/change/);
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
  assert.match(script, /state\.lang === 'cs' \? 'Zkopírováno' : 'Copied'/);
});

test('dashboard markup does not contain duplicate ids', () => {
  const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map((match) => match[1]);
  assert.equal(new Set(ids).size, ids.length);
});

test('dashboard keeps secondary guidance out of the primary content flow', () => {
  assert.doesNotMatch(html, /class="information-(?:grid|card)"/);
  assert.doesNotMatch(html, /Two ways to activate|Keep your slots tidy/);
  assert.match(html, /<details class="guidance-disclosure">/);
  assert.match(html, /How to use the activation key/);
  assert.match(html, /Billing help/);
  assert.match(html, /class="guidance-list"/);
});

test('pairing links use a short-lived fragment and survive OTP login', () => {
  assert.match(script, /PENDING_PAIRING_KEY/);
  assert.match(script, /window\.location\.hash\.replace\(\/\^#\//);
  assert.match(script, /sessionStorage\.setItem\(PENDING_PAIRING_KEY/);
  assert.match(script, /approve\/pairing#pair=/);
  assert.match(script, /history\.replaceState/);
  assert.match(html, /Scan the QR code shown by LongJumpReplay/);
  assert.match(html, /id="pairing-code"/);
});

test('QR approval is a standalone page with no dashboard chrome', () => {
  assert.match(pairingHtml, /class="account-page pairing-approval-page"/);
  assert.match(pairingHtml, /id="pairing-approve"/);
  assert.match(pairingHtml, /id="pairing-decline"/);
  assert.match(pairingHtml, /pairing-approval\.js/);
  assert.doesNotMatch(pairingHtml, /class="site-header"|data-dashboard-route|account\.js/);
  assert.match(pairingScript, /\/api\/portal\/pairing\/view/);
  assert.match(pairingScript, /\/api\/portal\/pairing\/approve/);
  assert.match(pairingScript, /\/api\/portal\/pairing\/decline/);
  assert.match(pairingScript, /\/api\/portal\/pairing\/result/);
  assert.match(css, /\.pairing-approval-page \[hidden\] \{ display: none !important; \}/);
});
