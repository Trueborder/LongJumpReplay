/** Test-only rehearsal against the named staging databases and isolated sandbox. */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { randomUUID, randomBytes, createHash, createHmac } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { build } from 'esbuild';
import assert from 'node:assert/strict';

const secrets = JSON.parse(readFileSync('secret-economysuite-staging.txt', 'utf8'));
const key = secrets.ECONOMYSUITE_STRIPE_KEY;
if (!/^(sk|rk|rkcs)_test_/.test(key || '')) throw new Error('This rehearsal refuses live Stripe keys.');
const origin = 'https://api-staging.tomaspisar.cz', customer = `es_rehearsal_${randomUUID()}`, uuid = randomUUID();
const token = randomBytes(32).toString('hex'), csrf = randomBytes(32).toString('hex');
const hash = value => createHash('sha256').update(value).digest('base64url');
const quote = value => `'${String(value).replaceAll("'", "''")}'`;
mkdirSync('.wrangler', { recursive: true });
async function stripe(path, fields) {
  const response = await fetch(`https://api.stripe.com/v1/${path}`, { method: fields ? 'POST' : 'GET', headers: { Authorization: `Bearer ${key}`, 'Stripe-Version': '2026-09-30.endive', ...(fields ? { 'Content-Type': 'application/x-www-form-urlencoded' } : {}) }, body: fields ? new URLSearchParams(fields) : undefined, signal: AbortSignal.timeout(15000) });
  if (!response.ok) { const failure = await response.json(); throw new Error(`Sandbox Stripe ${path.split('?')[0]} failed (${response.status}): ${failure.error?.code || ''} ${failure.error?.param || ''} ${failure.error?.message || ''}`); }
  return response.json();
}
function sql(binding, statement) {
  const filename = `.wrangler/es-rehearsal-${binding}.sql`;
  writeFileSync(filename, statement);
  try { execFileSync(process.execPath, ['node_modules/wrangler/bin/wrangler.js', 'd1', 'execute', binding, '--remote', '--env', 'staging', '--file', filename, '--json'], { encoding: 'utf8' }); }
  catch { throw new Error(`Staging ${binding} fixture operation failed`); }
}
async function portal(path, data) {
  const r = await fetch(`${origin}/api/economysuite/${path}`, { method: data ? 'POST' : 'GET', headers: { Cookie: `ljr-portal-session=${token}`, Origin: 'https://account.tomaspisar.cz', 'X-CSRF-Token': csrf, ...(data ? { 'Content-Type': 'application/json' } : {}) }, body: data ? JSON.stringify(data) : undefined });
  const value = await r.json();
  if (!r.ok) throw new Error(`Staging ${path} failed (${r.status}, ${value.error})`);
  return value;
}
async function bridge(path, payload) {
  const route = `/api/economysuite/bridge/${path}`, timestamp = Math.floor(Date.now() / 1000), nonce = randomUUID(), raw = JSON.stringify(payload);
  const signature = createHmac('sha256', secrets.ECONOMYSUITE_BRIDGE_SECRET).update(`${timestamp}\n${nonce}\n${route}\n${raw}`).digest('hex');
  const r = await fetch(origin + route, { method: 'POST', headers: { 'X-ES-Time': String(timestamp), 'X-ES-Nonce': nonce, 'X-ES-Signature': signature }, body: raw });
  if (!r.ok) throw new Error(`Staging bridge ${path} failed (${r.status})`);
  return r.json();
}
async function deliver(event) {
  const raw = JSON.stringify(event), timestamp = Math.floor(Date.now() / 1000);
  const signature = createHmac('sha256', secrets.ECONOMYSUITE_WEBHOOK_SECRET).update(`${timestamp}.${raw}`).digest('hex');
  for (let attempt = 0; attempt < 5; attempt++) {
    const response = await fetch(`${origin}/api/economysuite/stripe/webhook`, { method: 'POST', headers: { 'Stripe-Signature': `t=${timestamp},v1=${signature}` }, body: raw });
    if (response.status === 200) return;
    const result = await response.json();
    if (response.status !== 503 || attempt === 4) throw new Error(`Sandbox ${event.type} rejected (${response.status}, ${result.error}: ${result.message})`);
    await new Promise(resolve => setTimeout(resolve, 500));
  }
}
let published = null, checkout = null;
try {
  const bundled = await build({ entryPoints: ['src/crypto.ts'], bundle: true, platform: 'node', format: 'esm', write: false });
  writeFileSync('.wrangler/es-rehearsal-crypto.mjs', bundled.outputFiles[0].text);
  const { hashPassword } = await import('../.wrangler/es-rehearsal-crypto.mjs');
  const password = await hashPassword('Staging-only-test-password-123!'), time = Math.floor(Date.now() / 1000);
  sql('DB', `INSERT INTO customers(id,email,created_at,updated_at) VALUES(${quote(customer)},${quote(customer + '@example.com')},${time},${time}); INSERT INTO customer_password_credentials(customer_id,password_hash,created_at,updated_at,password_changed_at) VALUES(${quote(customer)},${quote(password)},${time},${time},${time}); INSERT INTO portal_sessions(id,customer_id,token_hash,created_at,expires_at,last_seen_at,csrf_token_hash) VALUES(${quote(randomUUID())},${quote(customer)},${quote(hash(token))},${time},${time + 1800},${time},${quote(hash(csrf))});`);
  const pair = await bridge('pair/start', { uuid, name: 'PortalTest' });
  const approved = await portal('pair/approve', { token: pair.token });
  await bridge('pair/confirm', { uuid, token: pair.token, confirmation: approved.confirmation });
  assert.equal((await portal('account')).link.uuid, uuid);
  console.log('PASS: live staging pairing requires website and game confirmation');
  const products = await stripe('products?active=true&limit=100&expand[]=data.default_price');
  const drafts = products.data.filter(p => p.metadata.es_product === 'economysuite');
  assert.equal(drafts.length, 6); assert.ok(drafts.every(p => p.metadata.es_published === 'false'));
  published = drafts.find(p => p.default_price.metadata.es_currency === 'coins' && p.default_price.metadata.es_amount === '1000');
  await stripe(`products/${published.id}`, { 'metadata[es_published]': 'true' });
  const packages = await portal('catalog'); assert.equal(packages.packages.length, 1);
  checkout = await portal('checkout', { price_id: published.default_price.id });
  const sessionId = checkout.url.match(/cs_test_[A-Za-z0-9]+/)?.[0]; assert.ok(sessionId);
  const session = await stripe(`checkout/sessions/${sessionId}`); assert.equal(session.metadata.player_uuid, uuid);
  assert.equal(session.metadata.customer_id, customer); assert.equal(session.metadata.purchase_type, 'economysuite_currency');
  writeFileSync('.wrangler/es-checkout-fixture.json', JSON.stringify({ _meta: { template_version: 0 }, fixtures: [
    { name: 'payment_page', method: 'get', path: `/v1/payment_pages/${sessionId}` },
    { name: 'payment_method', method: 'post', path: '/v1/payment_methods', params: { type: 'card', card: { token: 'tok_visa' }, billing_details: { email: session.customer_email, name: 'Portal Test', address: { line1: '354 Oyster Point Blvd', postal_code: '94080', city: 'South San Francisco', state: 'CA', country: 'US' } } } },
    { name: 'payment_page_confirm', method: 'post', path: `/v1/payment_pages/${sessionId}/confirm`, params: { payment_method: '${payment_method:id}', expected_amount: session.amount_total } },
  ] }));
  try { execFileSync(process.env.STRIPE_CLI_BIN || 'stripe', ['fixtures', '.wrangler/es-checkout-fixture.json', '--config', 'secret-economysuite-stripe.toml', '--api-version', '2026-08-26.dahlia'], { encoding: 'utf8', stdio: 'pipe' }); }
  catch (failure) { throw new Error(`Sandbox checkout fixture failed: ${String(failure.stderr || failure.message).replace(/\b[a-z]+_(?:test|live)_[A-Za-z0-9]+/g, '[redacted]')}`); }
  const paid = await stripe(`checkout/sessions/${sessionId}`); assert.equal(paid.payment_status, 'paid');
  const events = await stripe('events?type=checkout.session.completed&limit=100');
  const event = events.data.find(e => e.data.object.id === sessionId); assert.ok(event);
  await deliver(event); await deliver(event);
  const paidOrder = (await portal('orders')).orders.find(o => o.id === checkout.order_id); assert.equal(paidOrder.state, 'paid');
  const polled = await bridge('poll', {}), operations = polled.operations.filter(op => op.payload.order_id === checkout.order_id);
  assert.ok(operations.length >= 1); assert.ok(operations.every(op => op.payload.target_amount === 1000));
  sql('ECONOMYSUITE_DB', `SELECT COUNT(*) AS n FROM bridge_operations WHERE order_id=${quote(checkout.order_id)}`);
  console.log('PASS: real sandbox Checkout paid, webhook verified, duplicate delivery reconciled');
  for (const operation of operations) await bridge('ack', { id: operation.id, success: true, message: 'Test bridge acknowledgment; no Minecraft runtime' });
  const refund = await stripe('refunds', { payment_intent: paid.payment_intent, amount: '5000' }); assert.equal(refund.status, 'succeeded');
  await deliver({ id: `evt_rehearsal_${randomUUID()}`, type: 'charge.refunded', data: { object: { payment_intent: paid.payment_intent } } });
  const reversals = (await bridge('poll', {})).operations.filter(op => op.payload.order_id === checkout.order_id && op.payload.target_amount === 500);
  assert.ok(reversals.length >= 1); assert.equal((await portal('orders')).orders.find(o => o.id === checkout.order_id).state, 'partially_refunded');
  await stripe('refunds', { payment_intent: paid.payment_intent });
  await deliver({ id: `evt_rehearsal_${randomUUID()}`, type: 'charge.refunded', data: { object: { payment_intent: paid.payment_intent } } });
  assert.equal((await portal('orders')).orders.find(o => o.id === checkout.order_id).state, 'refunded');
  console.log('PASS: real partial and full Stripe refunds queued the correct currency targets');
} finally {
  if (published) await stripe(`products/${published.id}`, { 'metadata[es_published]': 'false' });
  sql('ECONOMYSUITE_DB', `DELETE FROM bridge_operations WHERE uuid=${quote(uuid)}; DELETE FROM store_orders WHERE customer_id=${quote(customer)}; DELETE FROM player_snapshots WHERE uuid=${quote(uuid)}; DELETE FROM player_links WHERE customer_id=${quote(customer)}; DELETE FROM pairing_challenges WHERE uuid=${quote(uuid)};`);
  sql('DB', `DELETE FROM portal_sessions WHERE customer_id=${quote(customer)}; DELETE FROM customer_password_credentials WHERE customer_id=${quote(customer)}; DELETE FROM customers WHERE id=${quote(customer)};`);
  console.log('Test fixtures removed from staging; all six currency packages remain unpublished.');
}
