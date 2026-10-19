/// <reference types="node" />
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';
import { readFileSync, readdirSync } from 'node:fs';
import { economySuite, packageFromProduct, targetCurrency } from './economysuite';
import type { Env } from './config';
import { sha256 } from './crypto';
import worker from './index';
import { TABLES, RULES_VERSION, maxStake, validInput, outcome } from './economysuite-games';
import { claimDaily, nextRewardReset } from './economysuite-daily';

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
      const sql = readFileSync(`economysuite-migrations/${migration}`, 'utf8').replace(/--[^\n]*/g, '').split(/;(?!\s*END\b)/i).map(statement => statement.replace(/\r?\n/g, ' ').trim()).filter(Boolean).join(';\n') + ';';
      await db.exec(sql);
    }
    for (const migration of readdirSync('migrations').filter(name => name.endsWith('.sql')).sort()) {
      const sql = readFileSync(`migrations/${migration}`, 'utf8').replace(/--[^\n]*/g, '').split(/;(?!\s*END\b)/i).map(statement => statement.replace(/\r?\n/g, ' ').trim()).filter(Boolean).join(';\n') + ';';
      await shared.exec(sql);
    }
    env = { DB: shared, ECONOMYSUITE_DB: db, PORTAL_ORIGIN: 'https://ljr.tomaspisar.cz', ECONOMYSUITE_PORTAL_ORIGIN: 'https://account.pantheon.tomaspisar.cz', STRIPE_SECRET_KEY: 'sk_test_fixture', ECONOMYSUITE_WEBHOOK_SECRET: 'whsec_test', ECONOMYSUITE_BRIDGE_SECRET: 'a'.repeat(64), ECONOMYSUITE_PURCHASES_ENABLED: 'true', VERIFICATION_PEPPER: 'test-pepper', MAIL_API_KEY: 're_test', MAIL_FROM: 'info@example.com', MAIL_FROM_NAME: 'Novaryn Solutions' } as Env;
  });
  afterEach(async () => { vi.unstubAllGlobals(); await runtime?.dispose(); });
  it('claims the free daily once under concurrent requests and safely delivers through compatible bridges', async () => {
    const db=env.ECONOMYSUITE_DB!;
    await db.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,?)').bind('owner',uuid,'Player',1).run();
    const responses=await Promise.all(Array.from({length:6},()=>economySuite(request('daily/claim',{tokens:999,uuid:'wrong'}),env,auth)));
    const results=await Promise.all(responses.map(response=>response.json() as Promise<{daily_reward:{amount:number;status:string}}>));
    const amount=results[0].daily_reward.amount;
    expect(amount).toBeGreaterThanOrEqual(1); expect(amount).toBeLessThanOrEqual(5);
    expect(results.every(result=>result.daily_reward.amount===amount&&result.daily_reward.status==='pending')).toBe(true);
    expect(await db.prepare('SELECT COUNT(*) FROM web_daily_rewards').first('COUNT(*)')).toBe(1);
    expect(await db.prepare("SELECT COUNT(*) FROM bridge_operations WHERE kind='web_daily'").first('COUNT(*)')).toBe(1);
    expect((await (await bridge('poll',{})).json() as {operations:unknown[]}).operations).toHaveLength(0);
    const polled=await (await bridge('poll',{web_daily_version:1})).json() as {operations:{id:string;payload:{tokens:number}}[];web_daily:{day:string}[]};
    expect(polled.operations).toHaveLength(1); expect(polled.operations[0].payload.tokens).toBe(amount);
    await bridge('ack',{id:polled.operations[0].id,success:true});
    await bridge('ack',{id:polled.operations[0].id,success:true});
    const account=await (await economySuite(request('account'),env,auth)).json() as {daily_reward:{available:boolean;status:string}};
    expect(account.daily_reward).toMatchObject({available:false,status:'delivered'});
    // Linking the same Minecraft UUID to another account cannot reroll today's reward.
    await db.prepare('UPDATE player_links SET customer_id=? WHERE uuid=?').bind('new-owner',uuid).run();
    const newAuth={...auth,authenticate:async()=>({customer:{id:'new-owner',email:'new@example.com'},credential:{password_hash:'unused'}})};
    const repeated=await (await economySuite(request('daily/claim',{}),env,newAuth)).json() as {daily_reward:{amount:number}};
    expect(repeated.daily_reward.amount).toBe(amount);
    expect(await db.prepare('SELECT COUNT(*) FROM web_daily_rewards').first('COUNT(*)')).toBe(1);
    const tomorrow=await claimDaily(db,uuid,'new-owner',nextRewardReset(Math.floor(Date.now()/1000)));
    expect(tomorrow.status).toBe('pending'); expect(tomorrow.available).toBe(false);
    expect(await db.prepare('SELECT COUNT(*) FROM web_daily_rewards').first('COUNT(*)')).toBe(2);
    const exported=await (await economySuite(request('export'),env,newAuth)).json() as {web_daily_rewards:{uuid:string;day:string}[]};
    expect(exported.web_daily_rewards).toHaveLength(1);
    expect(exported.web_daily_rewards[0].uuid).toBe(uuid);
    expect(exported.web_daily_rewards[0].day).toBe(tomorrow.day);
  });
  it('requires authentication, CSRF and a linked player for the website reward', async () => {
    expect((await economySuite(request('daily/claim',{}),env,{...auth,authenticate:async()=>null})).status).toBe(401);
    expect((await economySuite(request('daily/claim',{}),env,{...auth,mutation:async()=>false})).status).toBe(403);
    expect((await economySuite(request('daily/claim',{}),env,auth)).status).toBe(409);
    expect(await env.ECONOMYSUITE_DB!.prepare('SELECT COUNT(*) FROM web_daily_rewards').first('COUNT(*)')).toBe(0);
  });
  it('redirects old pages but keeps bridge and webhook requests on the original endpoint', async () => {
    const page = await worker.fetch(new Request('https://minecraft.tomaspisar.cz/economysuite/pair?test=1'), env);
    expect(page.status).toBe(308);
    expect(page.headers.get('Location')).toBe('https://account.pantheon.tomaspisar.cz/economysuite/pair?test=1');
    for (const route of ['/api/economysuite/bridge/poll', '/api/economysuite/stripe/webhook']) {
      const response = await worker.fetch(new Request('https://minecraft.tomaspisar.cz' + route, {method:'POST', body:'{}'}), env);
      expect(response.headers.has('Location')).toBe(false);
      expect(response.status).toBeGreaterThanOrEqual(400);
      expect(response.status).toBeLessThan(500);
    }
  });
  const request = (path: string, payload?: unknown) => new Request(`https://account.pantheon.tomaspisar.cz/api/economysuite/${path}`, payload ? { method: 'POST', body: JSON.stringify(payload) } : undefined);
  async function bridge(path: string, payload: unknown, nonce = crypto.randomUUID()) {
    const timestamp = Math.floor(Date.now() / 1000).toString(), raw = JSON.stringify(payload), route = `/api/economysuite/bridge/${path}`;
    const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(env.ECONOMYSUITE_BRIDGE_SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const signature = [...new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${timestamp}\n${nonce}\n${route}\n${raw}`)))].map(b => b.toString(16).padStart(2, '0')).join('');
    return economySuite(new Request(`https://account.pantheon.tomaspisar.cz${route}`, { method: 'POST', body: raw, headers: { 'X-ES-Time': timestamp, 'X-ES-Nonce': nonce, 'X-ES-Signature': signature } }), env, auth);
  }
  async function event(id: string, type: string, value: unknown) {
    const raw = JSON.stringify({ id, type, data: { object: value } }), timestamp = Math.floor(Date.now() / 1000);
    const key = await crypto.subtle.importKey('raw', new TextEncoder().encode('whsec_test'), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const signature = [...new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${timestamp}.${raw}`)))].map(b => b.toString(16).padStart(2, '0')).join('');
    return economySuite(new Request('https://account.pantheon.tomaspisar.cz/api/economysuite/stripe/webhook', { method: 'POST', body: raw, headers: { 'Stripe-Signature': `t=${timestamp},v1=${signature}` } }), env, auth);
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
  it('fulfills and refunds ranks as time, gates old plugins and never credits currency', async () => {
    const db=env.ECONOMYSUITE_DB!;
    await db.prepare("INSERT INTO store_orders(id,customer_id,uuid,player_name,price_id,currency_type,currency_amount,price_minor,session_id,created_at,updated_at,product_type,rank_id) VALUES('rank_order','owner',?,'Player','price_vip','rank',604800,3900,'cs_rank',1,1,'rank','vip')").bind(uuid).run();
    let refund=0;
    vi.stubGlobal('fetch',vi.fn(async(url:string)=>{
      if(url.includes('/checkout/sessions/'))return Response.json({currency:'czk',amount_total:3900,payment_status:'paid',payment_intent:'pi_rank',metadata:{order_id:'rank_order',purchase_type:'economysuite_rank',customer_id:'owner',player_uuid:uuid},line_items:{data:[{price:{id:'price_vip'},quantity:1}]}});
      if(url.includes('/payment_intents/'))return Response.json({latest_charge:{created:1700000000,amount_refunded:refund}});
      throw new Error('Unexpected payment request');
    }));
    const value={id:'cs_rank',metadata:{purchase_type:'economysuite_rank'}};
    expect((await event('rank_paid','checkout.session.completed',value)).status).toBe(200);
    expect((await event('rank_paid','checkout.session.completed',value)).status).toBe(200);
    const operations=await db.prepare('SELECT kind,payload FROM bridge_operations').all<{kind:string,payload:string}>();
    expect(operations.results).toHaveLength(1);expect(operations.results[0].kind).toBe('rank_purchase');
    expect(JSON.parse(operations.results[0].payload)).toMatchObject({rank:'vip',paid_at:1700000000000,duration_seconds:604800});
    const old=await (await bridge('poll',{})).json() as {operations:unknown[]};expect(old.operations).toHaveLength(0);
    const supported=await (await bridge('poll',{ranks_version:1})).json() as {operations:unknown[]};expect(supported.operations).toHaveLength(1);
    refund=1950;expect((await event('rank_refund','charge.refunded',{payment_intent:'pi_rank'})).status).toBe(200);
    const adjusted=await db.prepare('SELECT payload FROM bridge_operations WHERE revision=2').first<{payload:string}>();expect(JSON.parse(adjusted!.payload).duration_seconds).toBe(302400);
    expect(await db.prepare('SELECT currency_type FROM store_orders').first('currency_type')).toBe('rank');
  });
  it('rejects retired title mutations even for linked players',async()=>{
    await env.ECONOMYSUITE_DB!.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,1)').bind('owner',uuid,'Player').run();
    expect((await economySuite(request('cosmetics',{type:'title',id:'miner'}),env,auth)).status).toBe(400);
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
    const response = await economySuite(new Request('https://account.pantheon.tomaspisar.cz/api/economysuite/catalog'), env, { authenticate: async () => null, mutation: async () => false });
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
    await env.ECONOMYSUITE_DB!.prepare('INSERT INTO portal_registration_challenges(id,email,code_hash,setup_token_hash,purpose,created_at,expires_at,verified_at) VALUES(?,?,?,?,?,?,?,?)').bind('setup', 'owner@example.com', 'verified', await sha256(setup), 'registration', timestamp, timestamp + 300, timestamp).run();
    const api = async (path: string, payload: unknown) => worker.fetch(new Request(`https://account.pantheon.tomaspisar.cz${path}`, { method: 'POST', headers: { Origin: env.ECONOMYSUITE_PORTAL_ORIGIN!, 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }), env);
    const password = 'Test-password-123!';
    expect((await api('/api/portal/register/complete', { email: 'owner@example.com', setup_token: setup, password, password_confirmation: password, product: 'economysuite' })).status).toBe(200);
    expect(await env.ECONOMYSUITE_DB!.prepare('SELECT COUNT(*) AS n FROM portal_profiles').first('n')).toBe(0);
    const playerLogin = await api('/api/portal/password/login', { email: 'owner@example.com', password, product: 'economysuite' });
    expect(playerLogin.status).toBe(200);
    expect((await playerLogin.json() as { password_setup_required: boolean }).password_setup_required).toBe(false);
    expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM customers').first('n')).toBe(0);
    const ljrLogin = await worker.fetch(new Request('https://ljr.tomaspisar.cz/api/portal/password/login', { method: 'POST', headers: { Origin: env.PORTAL_ORIGIN }, body: JSON.stringify({ email: 'owner@example.com', password, product: 'economysuite' }) }), env);
    expect(ljrLogin.status).toBe(401);
    const cookie = playerLogin.headers.get('Set-Cookie')!.match(/__Host-es-session=[^;]+/)![0];
    const next = await worker.fetch(new Request('https://account.pantheon.tomaspisar.cz/login?product=economysuite&next=/economysuite/pair', { headers: { Cookie: cookie } }), env);
    expect(next.headers.get('Location')).toBe('https://account.pantheon.tomaspisar.cz/economysuite/pair');
    const setCookie = playerLogin.headers.get('Set-Cookie')!;
    const sessionCookie = setCookie.match(/__Host-es-session=[^;]+/)![0];
    const csrfCookie = setCookie.match(/__Host-es-csrf=([^;]+)/)![1];
    const exported = await worker.fetch(new Request('https://account.pantheon.tomaspisar.cz/api/portal/data-export', { headers: { Origin: env.ECONOMYSUITE_PORTAL_ORIGIN!, Cookie: sessionCookie } }), env);
    expect(exported.status).toBe(200);
    expect((await exported.json() as { account: { email: string } }).account.email).toBe('owner@example.com');
    const deletion = await worker.fetch(new Request('https://account.pantheon.tomaspisar.cz/api/portal/account/deletion-request', { method: 'POST', headers: { Origin: env.ECONOMYSUITE_PORTAL_ORIGIN!, Cookie: `${sessionCookie}; __Host-es-csrf=${csrfCookie}`, 'X-CSRF-Token': decodeURIComponent(csrfCookie), 'Content-Type': 'application/json' }, body: JSON.stringify({ password }) }), env);
    expect(deletion.status).toBe(200);
    expect(await env.ECONOMYSUITE_DB!.prepare("SELECT COUNT(*) AS n FROM privacy_requests WHERE type='deletion'").first('n')).toBe(1);
  });
  it('isolates registrations, passwords, cookies, resets and product APIs on both domains', async () => {
    const timestamp = Math.floor(Date.now()/1000), email='separate@example.com';
    const passwords={minecraft:'Minecraft-password-123!',ljr:'Replay-password-456!'};
    const call=(host:string,path:string,data?:unknown,headers:Record<string,string>={})=>worker.fetch(new Request(`https://${host === 'minecraft' ? 'account.pantheon' : host}.tomaspisar.cz${path}`,{method:data?'POST':'GET',headers:{Origin:`https://${host === 'minecraft' ? 'account.pantheon' : host}.tomaspisar.cz`,...headers},body:data?JSON.stringify(data):undefined}),env);
    for(const host of ['minecraft','ljr'] as const) {
      const db=host==='minecraft'?env.ECONOMYSUITE_DB!:env.DB, setup='setup-'+host;
      await db.prepare('INSERT INTO portal_registration_challenges(id,email,code_hash,setup_token_hash,purpose,created_at,expires_at,verified_at) VALUES(?,?,?,?,?,?,?,?)').bind(setup,email,'verified',await sha256(setup),'registration',timestamp,timestamp+300,timestamp).run();
      const result=await call(host,'/api/portal/register/complete',{email,setup_token:setup,password:passwords[host],password_confirmation:passwords[host],first_name:'Test',last_name:'Account',product:host==='minecraft'?'longjumpreplay':'economysuite'});
      expect(result.status).toBe(200);
      if(host==='minecraft')expect(await env.DB.prepare('SELECT count(*) n FROM customers').first('n')).toBe(0);
    }
    const mc=await env.ECONOMYSUITE_DB!.prepare('SELECT id FROM customers WHERE email=?').bind(email).first('id');
    const ljr=await env.DB.prepare('SELECT id FROM customers WHERE email=?').bind(email).first('id');
    expect(mc).not.toBe(ljr);
    const sessions:Record<string,string>={};
    for(const host of ['minecraft','ljr'] as const) {
      expect((await call(host,'/api/portal/password/login',{email,password:passwords[host==='minecraft'?'ljr':'minecraft'],product:'economysuite'})).status).toBe(401);
      const response=await call(host,'/api/portal/password/login',{email,password:passwords[host]});
      expect(response.status).toBe(200);
      const cookies=response.headers.get('Set-Cookie')!;
      expect(cookies).not.toContain('Domain=');expect(cookies).toContain('Secure');expect(cookies).toContain('HttpOnly');
      sessions[host]=cookies.match(new RegExp(`__Host-${host==='minecraft'?'es':'ljr'}-session=[^;]+`))![0];
      expect((await call(host,'/api/portal/account',undefined,{Cookie:sessions[host]})).status).toBe(200);
    }
    expect((await call('minecraft','/api/portal/account',undefined,{Cookie:sessions.ljr})).status).toBe(401);
    expect((await call('ljr','/api/portal/account',undefined,{Cookie:sessions.minecraft.replace('__Host-es-session','__Host-ljr-session')})).status).toBe(401);
    vi.stubGlobal('fetch', vi.fn(async()=>Response.json({id:'synthetic-email'})));
    expect((await call('minecraft','/api/portal/password/reset/request',{email})).status).toBe(200);
    expect(await env.ECONOMYSUITE_DB!.prepare('SELECT count(*) n FROM password_reset_codes').first('n')).toBe(1);
    expect(await env.DB.prepare('SELECT count(*) n FROM password_reset_codes').first('n')).toBe(0);
    expect((await call('minecraft','/api/portal/password/reset/request',{email} ,{Origin:'https://ljr.tomaspisar.cz'})).status).toBe(403);
    expect((await call('minecraft','/api/portal/billing',{})).status).toBe(404);
    expect((await call('minecraft','/api/license/request-code',{email})).status).toBe(404);
    expect((await call('ljr','/api/economysuite/account')).status).toBe(404);
    env.ECONOMYSUITE_ACCOUNTS_READY='false';
    expect((await call('minecraft','/api/portal/register/complete',{})).status).toBe(503);
    expect((await call('ljr','/api/portal/account',undefined,{Cookie:sessions.ljr})).status).toBe(200);
    env.ECONOMYSUITE_ACCOUNTS_READY='true';
    expect((await call('minecraft','/api/portal/logout',{}, {Cookie:sessions.minecraft})).status).toBe(200);
    expect((await call('ljr','/api/portal/account',undefined,{Cookie:sessions.ljr})).status).toBe(200);
    expect((await worker.fetch(new Request('https://account.tomaspisar.cz/login?product=economysuite'),env)).headers.get('Location')).toBe('https://account.pantheon.tomaspisar.cz/login');
    expect((await worker.fetch(new Request('https://account.tomaspisar.cz/api/portal/register/complete',{method:'POST',body:'{}'}),env)).status).toBe(410);
  });
  it('serves daily and weekly plugin quests and drops old stored batches without regranting anything', async () => {
    const db=env.ECONOMYSUITE_DB!;
    await db.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,?)').bind('owner',uuid,'Player',1).run();
    const daily={id:'stone',name:'Stone',progress:42,target:100,complete:false,reward_coins:50,points:1};
    await bridge('sync',{snapshots:[{uuid,progress:{tasks_version:2,daily:[daily],weekly:[{...daily,id:'weekly',complete:true}],cycles:{daily:'2026-10-20',weekly:'2026-10-19'}}}]});
    const response=await (await economySuite(request('account'),env,auth)).json() as {snapshot:{progress:{daily:unknown[];weekly:{complete:boolean}[];tasks?:unknown[]}}};
    expect(response.snapshot.progress.daily).toEqual([daily]);expect(response.snapshot.progress.weekly[0].complete).toBe(true);expect(response.snapshot.progress).not.toHaveProperty('tasks');
    await db.prepare('UPDATE player_snapshots SET payload=? WHERE uuid=?').bind(JSON.stringify({uuid,progress:{tasks:[daily]}}),uuid).run();
    const old=await (await economySuite(request('account'),env,auth)).json() as {snapshot:{progress:{daily:unknown[];weekly:unknown[];tasks?:unknown[]}}};
    expect(old.snapshot.progress.daily).toEqual([]);expect(old.snapshot.progress.weekly).toEqual([]);expect(old.snapshot.progress).not.toHaveProperty('tasks');
    expect(await db.prepare('SELECT COUNT(*) AS n FROM bridge_operations').first('n')).toBe(0);
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
    expect(await env.ECONOMYSUITE_DB!.prepare('SELECT leaderboard FROM player_links WHERE uuid=?').bind(uuid).first('leaderboard')).toBe(1);
    expect((await economySuite(request('pair/approve', { token: start.token }), env, auth)).status).toBe(409);
    const nonce = crypto.randomUUID();
    expect((await bridge('poll', {}, nonce)).status).toBe(200);
    expect((await bridge('poll', {}, nonce)).status).toBe(403);
  });
  it('keeps profiles private and excludes players who hide themselves from rankings', async () => {
    await env.ECONOMYSUITE_DB!.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,?)').bind('other', uuid, 'Other', 1).run();
    await env.ECONOMYSUITE_DB!.prepare('UPDATE player_links SET leaderboard=0 WHERE customer_id=?').bind('other').run();
    await bridge('sync', { snapshots: [{ uuid, statistics: { all_time: { playtime: 100 } } }] });
    const own = await (await economySuite(request('account'), env, auth)).json() as { snapshot: unknown };
    expect(own.snapshot).toBeNull();
    const ranking = await (await economySuite(request('leaderboard'), env, auth)).json() as { entries: unknown[] };
    expect(ranking.entries).toEqual([]);
  });
  it('shows linked players by default before sync and honors their later opt-out', async () => {
    const db=env.ECONOMYSUITE_DB!;
    await db.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,?)').bind('owner',uuid,'Player',1).run();
    const ranking=await (await economySuite(request('leaderboard'),env,auth)).json() as {entries:unknown[]};
    expect(ranking.entries).toEqual([{uuid,name:'Player',value:0}]);
    expect((await economySuite(request('privacy',{leaderboard:false}),env,auth)).status).toBe(200);
    const hidden=await (await economySuite(request('leaderboard'),env,auth)).json() as {entries:unknown[]};
    expect(hidden.entries).toEqual([]);
    await economySuite(request('privacy',{leaderboard:true}),env,auth);
    await bridge('sync',{snapshots:[{uuid,coins:900,tokens:200,statistics:{all_time:{playtime:100}}}]});
    const shown=await (await economySuite(request('leaderboard'),env,auth)).json() as {entries:unknown[]};
    expect(shown.entries).toEqual([{uuid,name:'Player',value:100}]);
  });
  it('backfills existing leaderboard defaults while preserving the protected link exactly', async () => {
    const db=env.ECONOMYSUITE_DB!;
    const protectedUuid='22222222-2222-4222-8222-222222222222';
    await db.prepare('INSERT INTO customers(id,email,created_at,updated_at) VALUES(?,?,1,1)').bind('protected','xpisar10@gmail.com').run();
    await db.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at,leaderboard) VALUES(?,?,?,?,0)').bind('protected',protectedUuid,'Protected',7).run();
    await db.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at,leaderboard) VALUES(?,?,?,?,0)').bind('owner',uuid,'Player',9).run();
    const before=await db.prepare('SELECT * FROM player_links WHERE customer_id=?').bind('protected').first();
    const sql=readFileSync('economysuite-migrations/0006_leaderboard_default_on.sql','utf8').replace(/--[^\n]*/g,'').replace(/\r?\n/g,' ');
    await db.exec(sql);
    expect(await db.prepare('SELECT * FROM player_links WHERE customer_id=?').bind('protected').first()).toEqual(before);
    expect(await db.prepare('SELECT * FROM player_links WHERE customer_id=?').bind('owner').first()).toEqual({customer_id:'owner',uuid,name:'Player',linked_at:9,leaderboard:1});
  });
  it('requires a valid payment signature and ignores LongJumpReplay events', async () => {
    expect((await economySuite(request('stripe/webhook', { id: 'forged' }), env, auth)).status).toBe(400);
    const raw = JSON.stringify({ id: 'evt_ljr', type: 'checkout.session.completed', data: { object: { metadata: {} } } });
    const timestamp = Math.floor(Date.now() / 1000), key = await crypto.subtle.importKey('raw', new TextEncoder().encode('whsec_test'), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const signature = [...new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${timestamp}.${raw}`)))].map(b => b.toString(16).padStart(2, '0')).join('');
    const response = await economySuite(new Request('https://account.pantheon.tomaspisar.cz/api/economysuite/stripe/webhook', { method: 'POST', body: raw, headers: { 'Stripe-Signature': `t=${timestamp},v1=${signature}` } }), env, auth);
    expect(response.status).toBe(200);
    expect(await env.ECONOMYSUITE_DB!.prepare('SELECT COUNT(*) AS count FROM bridge_operations').first('count')).toBe(0);
  });
  it('expires pairing tokens without accepting a username claim', async () => {
    await env.ECONOMYSUITE_DB!.prepare('INSERT INTO pairing_challenges(token_hash,uuid,name,expires_at) VALUES(?,?,?,?)').bind(await sha256('expired'), uuid, 'Player', 1).run();
    expect((await economySuite(request('pair/inspect', { token: 'expired', name: 'Player' }), env, auth)).status).toBe(410);
  });
  const bet = (key = crypto.randomUUID()) => ({ game: 'coin', currency: 'coins', stake: 100, choice: 'heads', rules_version: RULES_VERSION, idempotency_key: key });
  async function enableGames() {
    env.ENVIRONMENT = 'test'; env.PORTAL_ORIGIN = 'https://games-test.example'; env.ECONOMYSUITE_GAMES_ENABLED = 'true';
    await env.ECONOMYSUITE_DB!.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,?)').bind('owner', uuid, 'Player', 1).run();
    await bridge('poll', { games_version: RULES_VERSION, games_enabled: true });
  }
  it('uses exact integer tables and safe stake boundaries', () => {
    for (const table of Object.values(TABLES)) expect(table.reduce((sum,o)=>sum+o.probability*o.factor,0)).toBe(950);
    expect(validInput(bet())).toBe(true);
    expect(validInput({...bet(),stake:90})).toBe(false);
    expect(validInput({...bet(),currency:'tokens',stake:10})).toBe(true);
    expect(validInput({...bet(),stake:101})).toBe(false);
    expect(validInput({...bet(),game:'dice',choice:'10',stake:maxStake('dice','10')})).toBe(true);
    expect(validInput({...bet(),game:'dice',choice:'10',stake:maxStake('dice','10')+10})).toBe(false);
    for(const choice of ['heads','tails']) expect(Array.from({length:100},(_,i)=>outcome('coin',choice,i)!.factor).reduce((a,b)=>a+b,0)).toBe(950);
  });
  it('gates invalid production origins, disconnected servers and unsupported plugins', async () => {
    await enableGames();env.ENVIRONMENT='production';
    expect((await economySuite(request('games/rounds',bet()),env,auth)).status).toBe(503);
    env.ENVIRONMENT='test';await bridge('poll',{});
    expect((await economySuite(request('games/rounds',bet()),env,auth)).status).toBe(503);
    await bridge('poll',{games_version:RULES_VERSION,games_enabled:true});
    await env.ECONOMYSUITE_DB!.prepare('UPDATE bridge_status SET last_seen=1').run();
    expect((await economySuite(request('games/rounds',bet()),env,auth)).status).toBe(503);
    expect(await env.ECONOMYSUITE_DB!.prepare('SELECT COUNT(*) n FROM game_rounds').first('n')).toBe(0);
  });
  it('requires explicit production and server activation while retaining pending recovery', async () => {
    await enableGames(); env.ENVIRONMENT='production'; env.PORTAL_ORIGIN='https://account.pantheon.tomaspisar.cz';
    env.ECONOMYSUITE_GAMES_ENABLED='false';
    expect((await economySuite(request('games/rounds',bet()),env,auth)).status).toBe(503);
    env.ECONOMYSUITE_GAMES_ENABLED='true';
    await bridge('poll',{games_version:RULES_VERSION});
    let result=await economySuite(request('games/rounds',bet()),env,auth);
    expect((await result.json() as {error:string}).error).toBe('server_games_disabled');
    await bridge('poll',{games_version:RULES_VERSION,games_enabled:'true'});
    expect((await economySuite(request('games/rounds',bet()),env,auth)).status).toBe(503);
    await bridge('poll',{games_version:RULES_VERSION,games_enabled:true});
    const config=await (await economySuite(request('games/config'),env,auth)).json() as {enabled:boolean,server_enabled:boolean};
    expect(config).toMatchObject({enabled:true,server_enabled:true});
    const payload=bet(); result=await economySuite(request('games/rounds',payload),env,auth);
    expect(result.status).toBe(202);
    const {round}=await result.json() as {round:{id:string}};
    const poll=await (await bridge('poll',{games_version:RULES_VERSION,games_enabled:false})).json() as {operations:{id:string}[]};
    expect(poll.operations.map(operation=>operation.id)).toContain(round.id);
    env.ECONOMYSUITE_GAMES_ENABLED='false';
    expect((await economySuite(request('games/rounds',payload),env,auth)).status).toBe(200);
    expect(await env.ECONOMYSUITE_DB!.prepare('SELECT COUNT(*) n FROM game_rounds').first('n')).toBe(1);
  });
  it('enforces CSRF, ownership, one pending round and idempotent concurrent retries', async () => {
    await enableGames();const payload=bet();
    expect((await economySuite(request('games/rounds',payload),env,{...auth,mutation:async()=>false})).status).toBe(403);
    const responses=await Promise.all([economySuite(request('games/rounds',payload),env,auth),economySuite(request('games/rounds',payload),env,auth)]);
    const a=await responses[0].json() as {round:{id:string}},b=await responses[1].json() as {round:{id:string}};
    expect(a.round.id).toBe(b.round.id);
    expect((await economySuite(request('games/rounds',bet()),env,auth)).status).toBe(409);
    expect((await economySuite(request('games/rounds',{...payload,stake:110}),env,auth)).status).toBe(409);
    const other={...auth,authenticate:async()=>({customer:{id:'other',email:'other@example.com'},credential:{password_hash:'unused'}})};
    expect((await economySuite(request('games/rounds/'+a.round.id),env,other)).status).toBe(404);
    expect(await env.ECONOMYSUITE_DB!.prepare('SELECT COUNT(*) n FROM bridge_operations WHERE kind=\'game_round\'').first('n')).toBe(1);
    expect((await (await bridge('poll',{})).json() as {operations:unknown[]}).operations).toHaveLength(0);
  });
  it('accepts a durable payout after timeout and rejects inconsistent acknowledgments', async () => {
    await enableGames();const payload=bet();
    const {round}=await (await economySuite(request('games/rounds',payload),env,auth)).json() as {round:{id:string}};
    await env.ECONOMYSUITE_DB!.prepare('UPDATE game_rounds SET expires_at=1 WHERE id=?').bind(round.id).run();
    const result={rules_version:RULES_VERSION,state:'complete',roll:0,outcome:'heads',payout:190,net:90,balance:1090};
    expect((await bridge('ack',{id:round.id,game_result:{...result,payout:200}})).status).toBe(422);
    expect((await bridge('ack',{id:round.id,game_result:result})).status).toBe(200);
    expect((await bridge('ack',{id:round.id,game_result:result})).status).toBe(200);
    env.ENVIRONMENT='production';
    const replay=await (await economySuite(request('games/rounds',payload),env,auth)).json() as {round:{payout:number,state:string}};
    expect(replay.round.payout).toBe(190);expect(replay.round.state).toBe('complete');
    expect((await (await economySuite(request('games/rounds?filter=wins'),env,auth)).json() as {rounds:unknown[]}).rounds).toHaveLength(1);
    expect((await (await economySuite(request('export'),env,auth)).json() as {games:unknown[]}).games).toHaveLength(1);
  });
  it('retains expiry rejection and enforces cooldown after completion', async () => {
    await enableGames();const {round}=await (await economySuite(request('games/rounds',bet()),env,auth)).json() as {round:{id:string}};
    expect((await bridge('ack',{id:round.id,game_result:{rules_version:RULES_VERSION,state:'rejected',error:'expired'}})).status).toBe(200);
    expect((await economySuite(request('games/rounds',bet()),env,auth)).status).toBe(409);
    await env.ECONOMYSUITE_DB!.prepare('UPDATE game_rounds SET created_at=created_at-5').run();
    expect((await economySuite(request('games/rounds',bet()),env,auth)).status).toBe(202);
  });

  it('routes the isolated games portal and its script without exposing anonymous player data', async () => {
    env.ENVIRONMENT='test';env.ECONOMYSUITE_PORTAL_ORIGIN='https://games-test.example';
    const page=await worker.fetch(new Request(env.ECONOMYSUITE_PORTAL_ORIGIN+'/economysuite/games'),env);
    expect(page.status).toBe(302);expect(page.headers.get('Location')).toContain('/login?product=economysuite');
    env.ASSETS={fetch:async()=>new Response('fixture games script',{headers:{'Content-Type':'application/javascript'}}),connect:()=>{throw new Error('Unused fixture socket');}};
    const asset=await worker.fetch(new Request(env.ECONOMYSUITE_PORTAL_ORIGIN+'/economysuite/games.js'),env);
    expect(asset.status).toBe(200);expect(await asset.text()).toBe('fixture games script');
  });

});
