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

test('login composition keeps a centered backdrop and reduced-motion fallback', () => {
  assert.match(login, /class="login-backdrop"/);
  assert.match(styles, /portal-login-card-in/);
  assert.match(styles, /portal-login-backdrop-in/);
  assert.match(styles, /\.portal-login-page \.account-login \{ z-index: 31;/);
  assert.match(styles, /pointer-events: auto/);
  assert.match(styles, /#login-status:empty/);
  assert.match(styles, /\.login-actions-secondary \{ min-height: 0; padding-top: 0; \}/);
  assert.match(styles, /\.portal-login-page \.login-actions-secondary\[hidden\]/);
  assert.match(styles, /prefers-reduced-motion: reduce/);
});
