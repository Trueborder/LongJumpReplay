const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('tomaspisar.cz/account/economysuite/app.js', 'utf8');
const worker = fs.readFileSync('../licensing-api/src/index.ts', 'utf8');
const css = fs.readFileSync('tomaspisar.cz/account/economysuite/app.css', 'utf8');

function renderers(language = 'cs', linked = false, enabled = true) {
  const code = source.slice(source.indexOf('  const rankIds ='), source.indexOf('  function dailyRewardCard()'))
    + source.slice(source.indexOf('  function storePurchaseDialog()'), source.indexOf('  function purchases()'));
  const context = {
    t: (cs, en) => language === 'cs' ? cs : en,
    escape: value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[char])),
    money: value => String(value / 100) + ' Kč',
    account: linked === null ? null : linked ? {link:{name:'Player'}} : {},
    packages: ['vip','vipplus','mvp'].map((id,i) => ({id:'price_'+id,rank_id:id,currency:'rank',price_minor:[3900,6900,9900][i],checkoutable:true})),
    purchasesEnabled: enabled, route: 'store', rankPanel: () => '', panel: () => '', icon: () => '', currencyIcon: () => '', productLabel: () => ''
  };
  vm.createContext(context);
  vm.runInContext(code + '; globalThis.ui = {rankCard,rankDetail,rankComparison,rankPage,rankBenefits,store};', context);
  return context;
}

test('store keeps ranks out of the way; dedicated rank page has three identifiable cards', () => {
  const h = renderers();
  const html = h.ui.store();
  assert.doesNotMatch(html, /<table|es-rank-comparison|data-rank=|rank-details-dialog|es-rank-cards/);
  const rankPage = h.ui.rankPage();
  assert.equal((rankPage.match(/data-rank="/g) || []).length, 3);
  assert.match(rankPage, /rank-details-dialog/);
  const symbols = h.packages.map(pack => h.ui.rankCard(pack).match(/<svg[\s\S]*?<\/svg>/)[0]);
  assert.equal(new Set(symbols).size, 3);
});

test('comparison lives on its own public route with semantic coloured columns', () => {
  const html = renderers().ui.rankPage();
  assert.equal((html.match(/<table/g) || []).length, 1);
  assert.equal((html.match(/scope="row"/g) || []).length, 13);
  assert.match(html, /tabindex="0" role="region"/);
  for (const id of ['vip','vipplus','mvp']) assert.match(html, new RegExp('scope="col" class="es-tier-' + id + '"'));
  assert.match(worker, /'games', 'rank'(?:, '[a-z-]+')*\]\.includes\(category\)/);
  assert.match(worker, /!\['store', 'pair', 'rank'\]\.includes\(category\)/);
  assert.match(worker, /settings\|pair\|games\|rank(?:\|[a-z-]+)*\)\$/);
});

test('all rank dialogs list every benefit, inherited cosmetics and shared booster rules in both languages', () => {
  for (const language of ['cs', 'en']) {
    const h = renderers(language, true);
    for (const id of ['vip','vipplus','mvp']) {
      const html = h.ui.rankDetail(id);
      assert.equal((html.match(/<dt>/g) || []).length, 13);
      assert.match(html, /id="order-rank"/);
      assert.match(html, /168/);
      assert.match(html, /120/);
      assert.match(html, /price_/);
    }
    const mvp = h.ui.rankDetail('mvp');
    assert.match(mvp, /Golden halo|Zlatá svatozář/);
    assert.match(mvp, /Rainbow vortex|Duhový vír/);
    assert.match(mvp, /Pantheon aura/);
    assert.doesNotMatch(mvp, /Not included|Není součástí/);
  }
});

test('details do not bypass sign-in, pairing, disabled sales or uncheckoutable prices', () => {
  assert.match(renderers('cs', null).ui.rankDetail('vip'), /Přihlásit se pro nákup/);
  assert.match(renderers('cs', false).ui.rankDetail('vip'), /Nejdřív propojit hráče/);
  assert.doesNotMatch(renderers('cs', true, false).ui.rankDetail('vip'), /id="order-rank"/);
  const h = renderers('cs', true); h.packages[0].checkoutable = false;
  assert.doesNotMatch(h.ui.rankDetail('vip'), /id="order-rank"/);
  assert.equal(h.ui.rankDetail('<script>'), '');
  assert.equal(h.ui.rankCard({rank_id:'<script>'}), '');
});

test('dynamic price IDs are escaped; benefit preview is not a checkout request', () => {
  const h = renderers('cs', true); h.packages[0].id = '\"><script>alert(1)</script>';
  assert.doesNotMatch(h.ui.rankDetail('vip'), /<script>/);
  const previewHandler = source.slice(source.indexOf('const rankDialogNode ='), source.indexOf("$('#close-rank-details')?.addEventListener"));
  assert.doesNotMatch(previewHandler, /api\(/);
  assert.match(previewHandler, /rankDialogNode\.showModal\(\)/);
  assert.match(previewHandler, /rankDialogNode\.close\(\);\s+openPurchaseDialog/);
  assert.match(source, /pendingPurchase = \{ pack, button \}/);
  assert.match(source, /purchase-consent-form'\)\.reset/);
});

test('tier colours and narrow-screen modal layout remain explicit', () => {
  assert.match(css, /es-tier-vip\{--rank-accent:#eab308/);
  assert.match(css, /es-tier-vipplus\{--rank-accent:#22c55e/);
  assert.match(css, /es-tier-mvp\{--rank-accent:#7dd3fc/);
  assert.match(css, /es-rank-dialog::backdrop/);
  assert.match(css, /max-height:calc\(100dvh - 24px\)/);
  assert.match(css, /es-rank-cards\{grid-template-columns:1fr/);
});
