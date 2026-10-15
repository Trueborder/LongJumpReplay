const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname, '..', 'tomaspisar.cz');
const account = fs.readFileSync(path.join(root, 'assets/js/account/account.js'), 'utf8');
const portal = fs.readFileSync(path.join(root, 'account/economysuite/app.js'), 'utf8');

test('player registration moves the existing language control into one focused card', () => {
  const node = () => ({ dataset: {}, children: [], attributes: {}, append(...nodes) { this.children.push(...nodes); }, prepend(item) { this.children.unshift(item); }, setAttribute(key, value) { this.attributes[key] = value; }, replaceWith(item) { this.replacement = item; }, before(item) { this.previous = item; } });
  for (const language of ['cs', 'en']) {
    const nodes = Object.fromEntries(['.register-card', '.site-header .brand-mark', '[data-lang-toggle]', '#register-form-title', '.account-login'].map(key => [key, node()]));
    nodes['#register-form-title'].id = 'register-form-title';
    const classes = [];
    const document = { body: { classList: { add: value => classes.push(value) } }, documentElement: { lang: language }, querySelector: key => nodes[key], createElement: () => node() };
    const fn = account.slice(account.indexOf('  function compactPlayerRegistration()'), account.indexOf("  if (playerProduct && page === 'register')"));
    vm.runInNewContext(fn + '\ncompactPlayerRegistration();', { document });
    assert.deepEqual(classes, ['player-register-page']);
    const bar = nodes['.register-card'].children[0];
    assert.equal(bar.className, 'login-card-bar');
    assert.equal(bar.children[1], nodes['[data-lang-toggle]'], 'retain the translated button and its existing event listener');
    const heading = nodes['#register-form-title'].replacement;
    assert.equal(heading.textContent, language === 'cs' ? 'Vytvořit účet' : 'Create account');
    assert.equal(nodes['.account-login'].attributes['aria-labelledby'], heading.id);
    assert.equal(heading.previous.textContent, 'Pantheon / EconomySuite');
  }
});

test('pairing highlights exactly the current step and marks completion without a false next step', () => {
  const fn = portal.slice(portal.indexOf('  function onboardingGuide(active)'), portal.indexOf('  function pairingPage()'));
  for (const language of ['cs', 'en']) {
    const context = { t: (cs, en) => language === 'cs' ? cs : en, escape: value => value };
    vm.createContext(context);
    vm.runInContext(fn, context);
    for (const active of [1, 2, 3, 4]) {
      const html = vm.runInContext(`onboardingGuide(${active})`, context);
      assert.equal((html.match(/<li /g) || []).length, 3);
      assert.equal((html.match(/aria-current="step"/g) || []).length, active === 4 ? 0 : 1);
      assert.equal((html.match(/is-done/g) || []).length, active - 1);
      if (active < 4) assert.match(html, new RegExp(language === 'cs' ? 'Další krok' : 'Next step'));
    }
    assert.match(vm.runInContext("onboardingCard('title','body')", context), /is-next/);
    assert.doesNotMatch(vm.runInContext("onboardingCard('title','body','is-complete')", context), /is-next/);
  }
});

test('registration guide is gated by a valid pairing link or unexpired session and translates all steps', () => {
  const fn = account.slice(account.indexOf('  function showPlayerPairingGuide()'), account.indexOf("  if (playerProduct && page === 'register')"));
  const token = 'safe-dummy-pairing-token-123456789';
  for (const language of ['cs', 'en']) {
    for (const fixture of [
      { hash: '#pair=' + token, visible: true },
      { search: '?pair=' + token, visible: true },
      { pending: { token, expires: Date.now() + 60000 }, visible: true },
      { pending: { token, expires: Date.now() - 60000 }, visible: false },
      { hash: '#pair=invalid', visible: false },
      { visible: false }
    ]) {
      const element = tag => ({ tag, dataset: {}, children: [], attributes: {}, append(...nodes) { this.children.push(...nodes); }, setAttribute(key, value) { this.attributes[key] = value; } });
      const grid = element('div');
      const classes = [];
      const document = { body: { classList: { add: name => classes.push(name) } }, documentElement: { lang: language }, createElement: element, querySelector: () => grid };
      const sessionStorage = { getItem: () => JSON.stringify(fixture.pending || null) };
      vm.runInNewContext(fn + '\nshowPlayerPairingGuide();', { document, sessionStorage, URLSearchParams, location: { hash: fixture.hash || '', search: fixture.search || '' } });
      assert.equal(grid.children.length, fixture.visible ? 1 : 0);
      if (!fixture.visible) continue;
      assert.deepEqual(classes, ['player-pairing-page']);
      const [title, list] = grid.children[0].children;
      assert.equal(title.textContent, language === 'cs' ? 'Propojení účtu' : 'Pair your account');
      assert.equal(list.children.length, 3);
      assert.equal(list.children.filter(step => step.attributes['aria-current'] === 'step').length, 1);
      for (const step of list.children) {
        for (const copy of step.children[1].children) {
          assert.ok(copy.dataset.cs && copy.dataset.en, 'existing language switch can translate every instruction');
          assert.equal(copy.textContent, copy.dataset[language]);
          assert.ok(!copy.textContent.includes(token));
        }
      }
    }
  }
});
