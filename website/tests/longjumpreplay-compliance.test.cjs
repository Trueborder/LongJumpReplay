const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..', 'tomaspisar.cz');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

test('LongJumpReplay has separate legal pages and checkout evidence controls', () => {
  for (const file of [
    'legal/longjumpreplay-purchases/index.html', 'legal/longjumpreplay-refunds/index.html',
    'legal/longjumpreplay-activation/index.html', 'legal/longjumpreplay-updates/index.html',
    'legal/longjumpreplay-cookies/index.html', 'products/long-jump-replay/privacy/index.html',
  ]) assert.match(read(file), /LongJumpReplay|LONGJUMPREPLAY/);
  const checkout = read('account/checkout/index.html');
  assert.match(checkout, /Objednávka zavazující k platbě/);
  assert.match(checkout, /purchase-terms/);
  assert.match(checkout, /delivery-consent/);
  assert.match(checkout, /withdrawal-consent/);
  assert.doesNotMatch(checkout, /checked\s*=/i);
  const dashboard = read('account/dashboard/index.html');
  assert.match(dashboard, /export-data/);
  assert.match(dashboard, /deletion-form/);
  assert.match(dashboard, /Request account deletion|Požádat o výmaz účtu/);
});

test('LongJumpReplay public product no longer embeds a hardcoded Stripe pricing table', () => {
  const page = read('products/long-jump-replay/index.html');
  assert.doesNotMatch(page, /stripe-pricing-table|pricing-table-id|pk_live_/);
  assert.match(page, /ljr-public-catalog/);
  assert.match(page, /long-jump-replay\.js/);
});

test('LongJumpReplay browser assets contain no private Stripe or bridge secret names', () => {
  const files = ['account/checkout/checkout.js', 'assets/js/pages/long-jump-replay.js', 'assets/js/account/account.js'];
  for (const file of files) {
    const source = read(file);
    assert.doesNotMatch(source, /STRIPE_SECRET_KEY|STRIPE_WEBHOOK_SECRET|BRIDGE_SECRET|MAIL_API_KEY|AUTHORIZATION_PRIVATE_KEY/);
  }
});
