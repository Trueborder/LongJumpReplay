const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const script = fs.readFileSync(path.join(__dirname, '../tomaspisar.cz/assets/js/account/account.js'), 'utf8');

test('account messages contain UTF-8 text rather than mojibake', () => {
  assert.doesNotMatch(script, /[ÃÅÄ]|â€|â€¦|\uFFFD/);
  assert.match(script, /signingIn: 'Přihlašuji…'/);
  assert.match(script, /passwordLength: 'Použijte heslo dlouhé alespoň 12 znaků\.'/);
  assert.match(script, /resetSent: 'Pokud lze heslo obnovit, kód je na cestě\. Platí 10 minut\.'/);
  assert.match(script, /'Ověřit kód'/);
  assert.match(script, /'Ověřit e-mail'/);
  assert.match(script, /'Vytvořit účet'/);
});

test('every login mode assigns the correct Czech button label at runtime', () => {
  const body = script.match(/const setMode = \(mode\) => \{([\s\S]*?)\n    \};/);
  assert.ok(body, 'login mode handler must exist');
  const elements = new Map();
  const $ = (selector) => {
    if (!elements.has(selector)) elements.set(selector, { focus() {}, setAttribute() {} });
    return elements.get(selector);
  };
  const context = vm.createContext({ $, loginState: {}, setStatus() {}, setText(selector, en, cs) { $(selector).textContent = cs; } });
  for (const [mode, label] of [['password', 'Přihlásit se'], ['otp', 'Pokračovat'], ['reset', 'Poslat kód pro obnovu']]) {
    vm.runInContext(`((mode) => {${body[1]} })(${JSON.stringify(mode)})`, context);
    assert.equal($('#login-submit').textContent, label);
  }
});

test('dynamic auth labels preserve both translations when the language changes', () => {
  const helpers = [...script.matchAll(/const setText = \(selector, en, cs\) => \{([^\n]+)\};/g)];
  assert.equal(helpers.length, 2, 'login and registration each have a translation helper');
  for (const helper of helpers) {
    const element = { dataset: {} };
    const context = vm.createContext({ $: () => element, state: { lang: 'cs' } });
    vm.runInContext(`((selector, en, cs) => {${helper[1]} })('#submit', 'Sign in', 'Přihlásit se')`, context);
    assert.equal(element.textContent, 'Přihlásit se');
    assert.equal(element.dataset.en, 'Sign in');
    assert.equal(element.dataset.cs, 'Přihlásit se');
    element.textContent = element.dataset.en;
    assert.equal(element.textContent, 'Sign in');
  }
});
