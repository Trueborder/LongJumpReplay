const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..', 'tomaspisar.cz', 'account');
const login = fs.readFileSync(path.join(root, 'login', 'index.html'), 'utf8');
const account = fs.readFileSync(path.join(root, 'account.js'), 'utf8');

test('OTP login keeps the two-step email flow and recovery actions', () => {
  assert.match(login, /id="email-step"/);
  assert.match(login, /id="code-field"/);
  assert.match(login, /id="change-email"/);
  assert.match(login, /id="resend-code"/);
  assert.match(account, /\/api\/portal\/request-code/);
  assert.match(account, /\/api\/portal\/verify-code/);
  assert.match(account, /error\.status === 410/);
  assert.match(account, /replace\('\/dashboard\/overview'\)/);
});
