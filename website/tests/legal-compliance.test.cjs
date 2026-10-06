const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..', 'tomaspisar.cz');
const legal = ['index', 'operator', 'terms', 'economysuite-purchases', 'longjumpreplay-eula', 'refunds', 'complaints', 'cookies', 'privacy', 'accessibility'];

test('all legal routes render and link to the legal index', () => {
  for (const route of legal) {
    const file = route === 'index' ? path.join(root, 'legal', 'index.html') : path.join(root, 'legal', route, 'index.html');
    const html = fs.readFileSync(file, 'utf8');
    assert.match(html, /<main id="main">/);
    if (route !== 'index') assert.match(html, /href="\/legal\/"/);
    if (route !== 'privacy') assert.match(html, /href="\/legal\/privacy\/"/);
  }
});

test('privacy notice covers EconomySuite data, processors, transfers, retention, rights and automation', () => {
  const html = fs.readFileSync(path.join(root, 'legal', 'privacy', 'index.html'), 'utf8');
  for (const phrase of ['hash hesla', 'Minecraft UUID', 'Stripe', 'Cloudflare', 'Předávání mimo EHP', 'Uchování', 'Vaše práva', 'Automatizace a profilování', 'Děti a mladiství']) assert.match(html, new RegExp(phrase));
});

test('purchase terms expose payment, delivery, currency restrictions and Mojang disclaimer', () => {
  const html = fs.readFileSync(path.join(root, 'legal', 'economysuite-purchases', 'index.html'), 'utf8');
  for (const phrase of ['nemá hodnotu v reálných penězích', 'Objednávka zavazující k platbě', 'okamžité digitální dodání', 'Mojang ani Microsoft', 'refundace', 'doručení']) assert.match(html, new RegExp(phrase));
});

test('seller facts remain explicit placeholders instead of invented identity data', () => {
  const needed = fs.readFileSync(path.join(__dirname, '..', 'LEGAL_DATA_NEEDED.md'), 'utf8');
  for (const key of ['CONTROLLER_LEGAL_NAME', 'ICO', 'VAT_ID', 'REGISTERED_ADDRESS', 'LEGAL_EMAIL', 'VAT_TREATMENT']) assert.match(needed, new RegExp(`\\[\\[${key}\\]\\]`));
});

test('public assets do not contain server credentials', () => {
  const files = [];
  const visit = directory => { for (const entry of fs.readdirSync(directory, { withFileTypes: true })) { const file = path.join(directory, entry.name); if (entry.name === '.wrangler') continue; if (entry.isDirectory()) visit(file); else if (/\.(html|js|css|json)$/.test(entry.name)) files.push(file); } };
  visit(root);
  for (const file of files) {
    const content = fs.readFileSync(file, 'utf8');
    assert.doesNotMatch(content, /(?:sk_live_|sk_test_|whsec_|ECONOMYSUITE_BRIDGE_SECRET|STRIPE_SECRET_KEY|BEGIN PRIVATE KEY)/);
  }
});
