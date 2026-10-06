const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..', 'tomaspisar.cz', 'account');
const assetsRoot = path.resolve(__dirname, '..', 'tomaspisar.cz', 'assets');
const login = fs.readFileSync(path.join(root, 'login', 'index.html'), 'utf8');
const styles = fs.readFileSync(path.join(assetsRoot, 'css', 'pages', 'account.css'), 'utf8');
const account = fs.readFileSync(path.join(assetsRoot, 'js', 'account', 'account.js'), 'utf8');

test('OTP login keeps the two-step email flow and recovery actions', () => {
  assert.match(login, /id="email-step"/);
  assert.match(login, /id="code-field"/);
  assert.match(login, /id="change-email"/);
  assert.match(login, /id="resend-code"/);
  assert.match(login, /id="other-options-toggle"[^>]*aria-expanded="false"/);
  assert.match(login, /id="login-other-options"[^>]*hidden/);
  assert.match(login, /id="reset-actions"[^>]*hidden/);
  assert.doesNotMatch(login, /Having trouble\?/);
  assert.doesNotMatch(login, /class="login-info-button"/);
  assert.doesNotMatch(login, /id="login-info-tooltip"/);
  assert.doesNotMatch(login, /SECURE SIGN IN/);
  assert.doesNotMatch(login, /class="panel-icon"/);
  assert.doesNotMatch(login, /class="form-note"/);
  assert.match(account, /\/api\/portal\/request-code/);
  assert.match(account, /\/api\/portal\/verify-code/);
  assert.match(account, /error\.status === 410/);
  assert.match(account, /\/dashboard\/overview/);
});

test('login composition keeps one focused card and identifies the selected product', () => {
  assert.doesNotMatch(login, /class="login-backdrop"/);
  assert.doesNotMatch(login, /class="site-header"/);
  assert.doesNotMatch(login, /class="site-footer"/);
  assert.doesNotMatch(login, /class="account-intro login-context"/);
  assert.match(login, /class="login-destination-label"[^>]*>Signing in to</);
  assert.match(login, /data-login-product="longjumpreplay"/);
  assert.match(login, /data-login-product="economysuite"/);
  assert.match(account, /link\.dataset\.loginProduct === loginProduct/);
  assert.match(styles, /\.portal-login-page \.account-login-grid \{[^}]*place-items: center;/);
  assert.match(styles, /\.login-product-switcher a\[aria-current="page"\]/);
  assert.match(styles, /#login-status:empty/);
  assert.match(styles, /\.login-actions-secondary \{ min-height: 0; padding-top: 0; \}/);
  assert.match(styles, /\.portal-login-page \.login-actions-secondary\[hidden\]/);
});
