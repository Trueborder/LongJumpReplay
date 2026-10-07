/// <reference types="node" />
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';
import { readFileSync, readdirSync } from 'node:fs';
import { economySuite, packageFromProduct, targetCurrency } from './economysuite';
import type { Env } from './config';
import { sha256 } from './crypto';
import worker from './index';

describe('EconomySuite currency catalog', () => {
  const product = { active: true, name: 'Coin pack', metadata: { es_product: 'economysuite', es_server: 'pantheon', es_published: 'true' }, default_price: { id: 'price_es', active: true, currency: 'czk', type: 'one_time', unit_amount: 4900, metadata: { es_currency: 'coins', es_amount: '1000' } } };
  it('accepts only explicitly published one-time Pantheon packages', () => {
    expect(packageFromProduct(product)?.amount).toBe(1000);
    expect(packageFromProduct(product)?.checkoutable).toBe(true);
    expect(packageFromProduct({ ...product, default_price: { ...product.default_price, unit_amount: 490 } })?.checkoutable).toBe(false);
    expect(packageFromProduct({ ...product, metadata: {} })).toBeNull();
    expect(packageFromProduct({ ...product, default_price: { ...product.default_price, currency: 'eur' } })).toBeNull();
    expect(packageFromProduct({ ...product, default_price: { ...product.default_price, metadata: { es_currency: 'tokens', es_amount: '-1' } } })).toBeNull();
  });
  it('calculates cumulative partial refunds without floating point rounding', () => {
    expect(targetCurrency(10, 300, 100, '')).toBe(7);
    expect(targetCurrency(10, 300, 300, '')).toBe(0);
    expect(targetCurrency(10, 300, 0, 'needs_response')).toBe(0);
    expect(targetCurrency(10, 300, 100, 'won')).toBe(7);
    expect(targetCurrency(1_000_000_000, 999_999_999, 333_333_333, '')).toBe(666_666_667);
  });
});

describe('EconomySuite D1 ownership, pairing and fulfillment', () => {
  let runtime: Miniflare, env: Env;
  const uuid = '11111111-1111-4111-8111-111111111111';
  const auth = { authenticate: async () => ({ customer: { id: 'owner', email: 'owner@example.com' }, credential: { password_hash: 'unused' } }), mutation: async () => true };
  beforeEach(async () => {
    runtime = new Miniflare(convertV4MiniflareOptions({ modules: true, script: 'export default {fetch(){return new Response("ok")}}', d1Databases: ['DB', 'ES'], compatibilityDate: '2026-08-01' }));
    const db = await runtime.getD1Database('ES'), shared = await runtime.getD1Database('DB');
    for (const migration of readdirSync('economysuite-migrations').filter(name => name.endsWith('.sql')).sort()) {
      const sql = readFileSync(`economysuite-migrations/${migration}`, 'utf8').replace(/--[^\n]*/g, '').split(';').map(statement => statement.replace(/\r?\n/g, ' ').trim()).filter(Boolean).join(';\n') + ';';
      await db.exec(sql);
    }
    for (const migration of readdirSync('migrations').filter(name => name.endsWith('.sql')).sort()) {
      const sql = readFileSync(`migrations/${migration}`, 'utf8').replace(/--[^\n]*/g, '').split(';').map(statement => statement.replace(/\r?\n/g, ' ').trim()).filter(Boolean).join(';\n') + ';';
      await shared.exec(sql);
    }
    env = { DB: shared, ECONOMYSUITE_DB: db, PORTAL_ORIGIN: 'https://account.tomaspisar.cz', STRIPE_SECRET_KEY: 'sk_test_fixture', ECONOMYSUITE_WEBHOOK_SECRET: 'whsec_test', ECONOMYSUITE_BRIDGE_SECRET: 'a'.repeat(64), ECONOMYSUITE_PURCHASES_ENABLED: 'true', VERIFICATION_PEPPER: 'test-pepper', MAIL_API_KEY: 're_test', MAIL_FROM: 'info@example.com', MAIL_FROM_NAME: 'Novaryn Solutions' } as Env;
  });
  afterEach(async () => { vi.unstubAllGlobals(); await runtime?.dispose(); });
  const request = (path: string, payload?: unknown) => new Request(`https://account.tomaspisar.cz/api/economysuite/${path}`, payload ? { method: 'POST', body: JSON.stringify(payload) } : undefined);
  async function bridge(path: string, payload: unknown, nonce = crypto.randomUUID()) {
    const timestamp = Math.floor(Date.now() / 1000).toString(), raw = JSON.stringify(payload), route = `/api/economysuite/bridge/${path}`;
    const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(env.ECONOMYSUITE_BRIDGE_SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const signature = [...new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${timestamp}\n${nonce}\n${route}\n${raw}`)))].map(b => b.toString(16).padStart(2, '0')).join('');
    return economySuite(new Request(`https://account.tomaspisar.cz${route}`, { method: 'POST', body: raw, headers: { 'X-ES-Time': timestamp, 'X-ES-Nonce': nonce, 'X-ES-Signature': signature } }), env, auth);
  }
  async function event(id: string, type: string, value: unknown) {
    const raw = JSON.stringify({ id, type, data: { object: value } }), timestamp = Math.floor(Date.now() / 1000);
    const key = await crypto.subtle.importKey('raw', new TextEncoder().encode('whsec_test'), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const signature = [...new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${timestamp}.${raw}`)))].map(b => b.toString(16).padStart(2, '0')).join('');
    return economySuite(new Request('https://account.tomaspisar.cz/api/economysuite/stripe/webhook', { method: 'POST', body: raw, headers: { 'Stripe-Signature': `t=${timestamp},v1=${signature}` } }), env, auth);
  }
  it('fulfills paid sessions once, reconciles cumulative refunds and restores a won dispute', async () => {
    const db = env.ECONOMYSUITE_DB!;
    await db.prepare('INSERT INTO store_orders(id,customer_id,uuid,player_name,price_id,currency_type,currency_amount,price_minor,session_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)').bind('order', 'owner', uuid, 'Player', 'price_es', 'tokens', 10, 300, 'cs_es', 1, 1).run();
    let paid = false, refunded = 0, disputeStatus = 'needs_response';
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/checkout/sessions/')) return Response.json({ currency: 'czk', amount_total: 300, payment_status: paid ? 'paid' : 'unpaid', payment_intent: 'pi_es', metadata: { order_id: 'order', purchase_type: 'economysuite_currency', customer_id: 'owner', player_uuid: uuid }, line_items: { data: [{ price: { id: 'price_es' }, quantity: 1 }] } });
      if (url.includes('/payment_intents/')) return Response.json({ latest_charge: { amount_refunded: refunded, receipt_url: 'https://pay.stripe.com/receipts/fixture' } });
      if (url.includes('/disputes/')) return Response.json({ status: disputeStatus });
      throw new Error('Unexpected Stripe request');
    }));
    const checkout = { id: 'cs_es', metadata: { purchase_type: 'economysuite_currency' } };
    expect((await event('evt_unpaid', 'checkout.session.completed', checkout)).status).toBe(200);
    expect(await db.prepare('SELECT COUNT(*) AS n FROM bridge_operations').first('n')).toBe(0);
    paid = true;
    expect((await event('evt_paid', 'checkout.session.async_payment_succeeded', checkout)).status).toBe(200);
    expect((await event('evt_paid', 'checkout.session.async_payment_succeeded', checkout)).status).toBe(200);
    expect(await db.prepare('SELECT COUNT(*) AS n FROM bridge_operations').first('n')).toBe(1);
    refunded = 100;
    expect((await event('evt_refund', 'charge.refunded', { payment_intent: 'pi_es' })).status).toBe(200);
    expect(await db.prepare('SELECT target_amount FROM store_orders').first('target_amount')).toBe(7);
    expect((await event('evt_dispute', 'charge.dispute.created', { id: 'dp_es', payment_intent: 'pi_es' })).status).toBe(200);
    expect(await db.prepare('SELECT target_amount FROM store_orders').first('target_amount')).toBe(0);
    disputeStatus = 'won';
    expect((await event('evt_won', 'charge.dispute.closed', { id: 'dp_es', payment_intent: 'pi_es' })).status).toBe(200);
    expect(await db.prepare('SELECT target_amount FROM store_orders').first('target_amount')).toBe(7);
    const operations = await (await bridge('poll', {})).json() as { operations: { id: string }[] };
    for (const op of operations.operations) expect((await bridge('ack', { id: op.id, success: true })).status).toBe(200);
    expect(await db.prepare('SELECT delivered_revision=revision AS delivered FROM store_orders').first('delivered')).toBe(1);
    expect((await event('evt_other', 'charge.refunded', { payment_intent: 'pi_ljr' })).status).toBe(200);
  });
  it('rejects mismatched payment metadata and keeps purchase history owned by the account', async () => {
    const db = env.ECONOMYSUITE_DB!;
    await db.prepare('INSERT INTO store_orders(id,customer_id,uuid,player_name,price_id,currency_type,currency_amount,price_minor,session_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)').bind('order', 'other', uuid, 'Other', 'price_es', 'coins', 100, 300, 'cs_es', 1, 1).run();
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ metadata: { order_id: 'order', customer_id: 'owner' } })));
    expect((await event('evt_tampered', 'checkout.session.completed', { id: 'cs_es', metadata: { purchase_type: 'economysuite_currency' } })).status).toBe(409);
    const history = await (await economySuite(request('orders'), env, auth)).json() as { orders: unknown[] };
    expect(history.orders).toEqual([]);
    expect(await db.prepare('SELECT COUNT(*) AS n FROM bridge_operations').first('n')).toBe(0);
  });
  it('recovers interrupted checkout mapping and reconciles disputes that precede checkout delivery', async () => {
    const db = env.ECONOMYSUITE_DB!;
    await db.prepare('INSERT INTO store_orders(id,customer_id,uuid,player_name,price_id,currency_type,currency_amount,price_minor,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)').bind('order', 'owner', uuid, 'Player', 'price_es', 'coins', 1000, 300, 1, 1).run();
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/checkout/sessions/')) return Response.json({ currency: 'czk', amount_total: 300, payment_status: 'paid', payment_intent: 'pi_es', metadata: { order_id: 'order', purchase_type: 'economysuite_currency', customer_id: 'owner', player_uuid: uuid }, line_items: { data: [{ price: { id: 'price_es' }, quantity: 1 }] } });
      if (url.includes('/payment_intents/')) return Response.json({ latest_charge: { disputed: true, amount_refunded: 0 } });
      if (url.includes('/disputes?')) return Response.json({ data: [{ id: 'dp_early', status: 'needs_response' }] });
      throw new Error('Unexpected Stripe request');
    }));
    expect((await event('evt_early', 'charge.dispute.created', { id: 'dp_early', payment_intent: 'pi_es' })).status).toBe(200);
    expect((await event('evt_late_checkout', 'checkout.session.completed', { id: 'cs_es', metadata: { order_id: 'order', purchase_type: 'economysuite_currency' } })).status).toBe(200);
    expect(await db.prepare('SELECT session_id FROM store_orders').first('session_id')).toBe('cs_es');
    expect(await db.prepare('SELECT target_amount FROM store_orders').first('target_amount')).toBe(0);
    expect(await db.prepare('SELECT state FROM store_orders').first('state')).toBe('disputed');
  });
  it('requires authentication and CSRF for player mutations', async () => {
    expect((await economySuite(request('account'), env, { ...auth, authenticate: async () => null })).status).toBe(401);
    expect((await economySuite(request('privacy', { leaderboard: true }), env, { ...auth, mutation: async () => false })).status).toBe(403);
  });
  it('reports live bridge states and deduplicates player refresh requests', async () => {
    const db = env.ECONOMYSUITE_DB!, timestamp = Math.floor(Date.now() / 1000);
    await db.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,?)').bind('owner', uuid, 'Player', timestamp).run();
    await db.prepare("INSERT INTO bridge_status(server,last_seen) VALUES('pantheon',?)").bind(timestamp).run();
    let account = await (await economySuite(request('account'), env, auth)).json() as { server_status: string };
    expect(account.server_status).toBe('connected');
    await db.prepare("UPDATE bridge_status SET last_seen=? WHERE server='pantheon'").bind(timestamp - 30).run();
    account = await (await economySuite(request('account'), env, auth)).json() as { server_status: string };
    expect(account.server_status).toBe('connecting');
    await db.prepare("UPDATE bridge_status SET last_seen=? WHERE server='pantheon'").bind(timestamp - 100).run();
    account = await (await economySuite(request('account'), env, auth)).json() as { server_status: string };
    expect(account.server_status).toBe('disconnected');
    const first = await (await economySuite(request('refresh', {}), env, auth)).json() as { operation_id: string };
    const second = await (await economySuite(request('refresh', {}), env, auth)).json() as { operation_id: string };
    expect(second.operation_id).toBe(first.operation_id);
    expect(await db.prepare("SELECT COUNT(*) AS n FROM bridge_operations WHERE kind='refresh'").first('n')).toBe(1);
  });
  it('rejects checkout without legal acceptance and persists the accepted purchase evidence', async () => {
    const db = env.ECONOMYSUITE_DB!;
    await db.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,?)').bind('owner', uuid, 'Player', 1).run();
    let checkoutBody: URLSearchParams | null = null;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes('/products?')) return Response.json({ data: [{ active: true, name: 'Tokens', metadata: { es_product: 'economysuite', es_server: 'pantheon', es_published: 'true' }, default_price: { id: 'price_es', active: true, currency: 'czk', type: 'one_time', unit_amount: 1990, metadata: { es_currency: 'tokens', es_amount: '10' } } }], has_more: false });
      if (url.endsWith('/checkout/sessions') && init?.body) checkoutBody = new URLSearchParams(String(init.body));
      return Response.json({ id: 'cs_es', url: 'https://checkout.stripe.com/c/pay' });
    }));
    expect((await economySuite(request('checkout', { price_id: 'price_es' }), env, auth)).status).toBe(422);
    const result = await economySuite(request('checkout', { price_id: 'price_es', accepted_purchase_terms: true, immediate_delivery_requested: true, withdrawal_rights_acknowledged: true, displayed_price_minor: 1990, displayed_currency: 'czk', idempotency_key: 'checkout-test-123456', policy_versions: { privacy: '2026-10-06', purchase: '2026-10-06', refund: '2026-10-06', delivery: '2026-10-06' } }), env, auth);
    expect(result.status).toBe(200);
    const sentCheckoutBody = checkoutBody as unknown as URLSearchParams;
    expect(sentCheckoutBody.get('client_reference_id')).toBeTruthy();
    expect(sentCheckoutBody.has('integration_identifier')).toBe(false);
    const retry = await economySuite(request('checkout', { price_id: 'price_es', accepted_purchase_terms: true, immediate_delivery_requested: true, withdrawal_rights_acknowledged: true, displayed_price_minor: 1990, displayed_currency: 'czk', idempotency_key: 'checkout-test-123456', policy_versions: { privacy: '2026-10-06', purchase: '2026-10-06', refund: '2026-10-06', delivery: '2026-10-06' } }), env, auth);
    expect(retry.status).toBe(200);
    expect((await retry.json() as { idempotent?: boolean }).idempotent).toBe(true);
    expect(await db.prepare('SELECT policy_version,immediate_delivery_requested,withdrawal_rights_acknowledged,displayed_price_minor FROM store_orders').first()).toMatchObject({ policy_version: '2026-10-06', immediate_delivery_requested: 1, withdrawal_rights_acknowledged: 1, displayed_price_minor: 1990 });
    expect(await db.prepare('SELECT COUNT(*) AS n FROM purchase_consents').first('n')).toBe(1);
    expect(await db.prepare('SELECT status FROM order_confirmations').first('status')).toBe('sent');
  });
  it('serves the public EconomySuite catalogue without authentication', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ data: [{ active: true, name: 'Public tokens', metadata: { es_product: 'economysuite', es_server: 'pantheon', es_published: 'true' }, default_price: { id: 'price_public', active: true, currency: 'czk', type: 'one_time', unit_amount: 300, metadata: { es_currency: 'tokens', es_amount: '10' } } }], has_more: false })));
    const response = await economySuite(new Request('https://account.tomaspisar.cz/api/economysuite/catalog'), env, { authenticate: async () => null, mutation: async () => false });
    expect(response.status).toBe(200);
    expect((await response.json() as { packages: { id: string }[] }).packages[0].id).toBe('price_public');
  });
  it('rejects CZK packages below Stripe minimum before creating an order', async () => {
    const db = env.ECONOMYSUITE_DB!;
    await db.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,?)').bind('owner', uuid, 'Player', 1).run();
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/products?')) return Response.json({ data: [{ active: true, name: 'Micro tokens', metadata: { es_product: 'economysuite', es_server: 'pantheon', es_published: 'true' }, default_price: { id: 'price_micro', active: true, currency: 'czk', type: 'one_time', unit_amount: 490, metadata: { es_currency: 'tokens', es_amount: '10' } } }], has_more: false });
      throw new Error('Stripe Checkout must not be called for a sub-minimum package');
    }));
    const response = await economySuite(request('checkout', { price_id: 'price_micro', accepted_purchase_terms: true, immediate_delivery_requested: true, withdrawal_rights_acknowledged: true, displayed_price_minor: 490, displayed_currency: 'czk', idempotency_key: 'checkout-micro-123456', policy_versions: { privacy: '2026-10-06', purchase: '2026-10-06', refund: '2026-10-06', delivery: '2026-10-06' } }), env, auth);
    expect(response.status).toBe(422);
    expect(await response.json()).toMatchObject({ error: 'stripe_minimum' });
    expect(await db.prepare('SELECT COUNT(*) AS n FROM store_orders').first('n')).toBe(0);
  });
  it('registers players without a real-name profile and retains the LongJumpReplay setup gate', async () => {
    const timestamp = Math.floor(Date.now() / 1000), setup = 'verified-test-registration';
    await env.DB.prepare('INSERT INTO portal_registration_challenges(id,email,code_hash,setup_token_hash,purpose,created_at,expires_at,verified_at) VALUES(?,?,?,?,?,?,?,?)').bind('setup', 'owner@example.com', 'verified', await sha256(setup), 'registration', timestamp, timestamp + 300, timestamp).run();
    const api = async (path: string, payload: unknown) => worker.fetch(new Request(`https://account.tomaspisar.cz${path}`, { method: 'POST', headers: { Origin: env.PORTAL_ORIGIN, 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }), env);
    const password = 'Test-password-123!';
    expect((await api('/api/portal/register/complete', { email: 'owner@example.com', setup_token: setup, password, password_confirmation: password, product: 'economysuite' })).status).toBe(200);
    expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM portal_profiles').first('n')).toBe(0);
    const playerLogin = await api('/api/portal/password/login', { email: 'owner@example.com', password, product: 'economysuite' });
    expect(playerLogin.status).toBe(200);
    expect((await playerLogin.json() as { password_setup_required: boolean }).password_setup_required).toBe(false);
    const ljrLogin = await api('/api/portal/password/login', { email: 'owner@example.com', password });
    expect((await ljrLogin.json() as { password_setup_required: boolean }).password_setup_required).toBe(true);
    const cookie = playerLogin.headers.get('Set-Cookie')!.match(/ljr-portal-session=[^;]+/)![0];
    const next = await worker.fetch(new Request('https://account.tomaspisar.cz/login?product=economysuite&next=/economysuite/pair', { headers: { Cookie: cookie } }), env);
    expect(next.headers.get('Location')).toBe('https://account.tomaspisar.cz/economysuite/pair');
    const setCookie = playerLogin.headers.get('Set-Cookie')!;
    const sessionCookie = setCookie.match(/ljr-portal-session=[^;]+/)![0];
    const csrfCookie = setCookie.match(/ljr-portal-csrf=([^;]+)/)![1];
    const exported = await worker.fetch(new Request('https://account.tomaspisar.cz/api/portal/data-export', { headers: { Origin: env.PORTAL_ORIGIN, Cookie: sessionCookie } }), env);
    expect(exported.status).toBe(200);
    expect((await exported.json() as { customer: { email: string } }).customer.email).toBe('owner@example.com');
    const deletion = await worker.fetch(new Request('https://account.tomaspisar.cz/api/portal/account/deletion-request', { method: 'POST', headers: { Origin: env.PORTAL_ORIGIN, Cookie: `${sessionCookie}; ljr-portal-csrf=${csrfCookie}`, 'X-CSRF-Token': decodeURIComponent(csrfCookie), 'Content-Type': 'application/json' }, body: JSON.stringify({ password }) }), env);
    expect(deletion.status).toBe(200);
    expect(await env.DB.prepare("SELECT COUNT(*) AS n FROM privacy_requests WHERE type='deletion'").first('n')).toBe(1);
  });
  it('only stores the allowlisted gameplay snapshot and never publishes secrets', async () => {
    await env.ECONOMYSUITE_DB!.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,?)').bind('owner', uuid, 'Player', 1).run();
    await bridge('sync', { snapshots: [{ uuid, auth_pin: 'SECRET-PIN', email: 'hidden@example.com', coins: 5, daily: { day: 1, auth_hash: 'SECRET-HASH' }, statistics: { all_time: { playtime: 100, private_note: 'SECRET-NOTE' } } }] });
    const own = await (await economySuite(request('account'), env, auth)).json() as { snapshot: { coins: number } };
    expect(own.snapshot.coins).toBe(5);
    expect(JSON.stringify(own.snapshot)).not.toContain('SECRET');
    expect(JSON.stringify(own.snapshot)).not.toContain('hidden@example.com');
  });
  it('requires both website approval and in-game confirmation, and rejects bridge replay', async () => {
    const start = await (await bridge('pair/start', { uuid, name: 'Player' })).json() as { token: string };
    expect((await bridge('pair/confirm', { uuid, token: start.token, confirmation: 'wrong' })).status).toBe(400);
    const approved = await (await economySuite(request('pair/approve', { token: start.token }), env, auth)).json() as { confirmation: string };
    expect((await bridge('pair/confirm', { uuid, token: start.token, confirmation: approved.confirmation })).status).toBe(200);
    expect(await env.ECONOMYSUITE_DB!.prepare('SELECT customer_id FROM player_links WHERE uuid=?').bind(uuid).first('customer_id')).toBe('owner');
    expect((await economySuite(request('pair/approve', { token: start.token }), env, auth)).status).toBe(409);
    const nonce = crypto.randomUUID();
    expect((await bridge('poll', {}, nonce)).status).toBe(200);
    expect((await bridge('poll', {}, nonce)).status).toBe(403);
  });
  it('keeps profiles private and excludes non-consenting players from rankings', async () => {
    await env.ECONOMYSUITE_DB!.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,?)').bind('other', uuid, 'Other', 1).run();
    await bridge('sync', { snapshots: [{ uuid, statistics: { all_time: { playtime: 100 } } }] });
    const own = await (await economySuite(request('account'), env, auth)).json() as { snapshot: unknown };
    expect(own.snapshot).toBeNull();
    const ranking = await (await economySuite(request('leaderboard'), env, auth)).json() as { entries: unknown[] };
    expect(ranking.entries).toEqual([]);
  });
  it('requires a valid payment signature and ignores LongJumpReplay events', async () => {
    expect((await economySuite(request('stripe/webhook', { id: 'forged' }), env, auth)).status).toBe(400);
    const raw = JSON.stringify({ id: 'evt_ljr', type: 'checkout.session.completed', data: { object: { metadata: {} } } });
    const timestamp = Math.floor(Date.now() / 1000), key = await crypto.subtle.importKey('raw', new TextEncoder().encode('whsec_test'), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const signature = [...new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${timestamp}.${raw}`)))].map(b => b.toString(16).padStart(2, '0')).join('');
    const response = await economySuite(new Request('https://account.tomaspisar.cz/api/economysuite/stripe/webhook', { method: 'POST', body: raw, headers: { 'Stripe-Signature': `t=${timestamp},v1=${signature}` } }), env, auth);
    expect(response.status).toBe(200);
    expect(await env.ECONOMYSUITE_DB!.prepare('SELECT COUNT(*) AS count FROM bridge_operations').first('count')).toBe(0);
  });
  it('expires pairing tokens without accepting a username claim', async () => {
    await env.ECONOMYSUITE_DB!.prepare('INSERT INTO pairing_challenges(token_hash,uuid,name,expires_at) VALUES(?,?,?,?)').bind(await sha256('expired'), uuid, 'Player', 1).run();
    expect((await economySuite(request('pair/inspect', { token: 'expired', name: 'Player' }), env, auth)).status).toBe(410);
  });
});
