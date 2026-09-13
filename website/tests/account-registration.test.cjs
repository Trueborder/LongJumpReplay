const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..', 'tomaspisar.cz', 'account');
const assetsRoot = path.resolve(__dirname, '..', 'tomaspisar.cz', 'assets');
const register = fs.readFileSync(path.join(root, 'register', 'index.html'), 'utf8');
const login = fs.readFileSync(path.join(root, 'login', 'index.html'), 'utf8');
const account = fs.readFileSync(path.join(assetsRoot, 'js', 'account', 'account.js'), 'utf8');

test('registration collects the verified email, profile and strong password', () => {
  assert.match(register, /data-portal-page="register"/);
  assert.match(register, /id="register-email"/);
  assert.match(register, /id="register-code"/);
  assert.match(register, /id="register-first-name"/);
  assert.match(register, /id="register-last-name"/);
  assert.match(register, /id="register-club-name"/);
  assert.match(register, /id="register-password-confirmation"/);
  assert.match(account, /\/api\/portal\/register\/request-code/);
  assert.match(account, /\/api\/portal\/register\/verify-code/);
  assert.match(account, /\/api\/portal\/register\/complete/);
  assert.match(login, /href="\/register"/);
});
