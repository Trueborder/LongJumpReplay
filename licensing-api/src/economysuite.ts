import type { Env } from './config';
import { generateToken, sha256, timingSafeEqual, verifyPassword } from './crypto';
import { now, rateLimit } from './db';
import { verifySignature } from './stripe';

export interface PlayerAuth { customer: { id: string; email: string }; credential: { password_hash: string } | null }
export interface EconomyAuth { authenticate(request: Request): Promise<PlayerAuth | null>; mutation(request: Request): Promise<boolean> }
export type Currency = 'coins' | 'tokens';
interface Package { id: string; name: string; description: string; currency: Currency; amount: number; price_minor: number; sort: number }
interface Link { customer_id: string; uuid: string; name: string; leaderboard: number }
interface Order { id: string; customer_id: string; uuid: string; player_name: string; price_id: string; currency_type: Currency; currency_amount: number; price_minor: number; session_id: string | null; payment_intent: string | null; dispute_id: string | null; paid: number; target_amount: number; revision: number; delivered_revision: number; state: string; receipt_url: string | null; created_at: number }
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const reply = (data: unknown, status = 200) => Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } });
const error = (code: string, message: string, status = 400) => reply({ error: code, message }, status);
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const s = (value: unknown) => typeof value === 'string' ? value : '';
const integer = (value: unknown, min = 0, max = 1_000_000_000): number | null => Number.isSafeInteger(Number(value)) && Number(value) >= min && Number(value) <= max ? Number(value) : null;
const pick = (value: unknown, keys: string[]) => Object.fromEntries(keys.filter(key => Object.hasOwn(object(value), key)).map(key => [key, object(value)[key]]));
function playerSnapshot(value: Record<string, unknown>): Record<string, unknown> {
  const out = pick(value, ['uuid', 'coins', 'tokens', 'pending_tokens', 'active_minutes', 'eligible', 'account_created_at', 'mailbox_count', 'auction_count']);
  out.level = pick(value.level, ['level', 'xp']); out.job = pick(value.job, ['id', 'display', 'level']);
  out.debt = pick(value.debt, ['coins', 'tokens']); out.daily = pick(value.daily, ['day', 'last_day', 'revives']);
  const metrics = ['playtime', 'blocks_mined', 'blocks_placed', 'mobs_killed', 'deaths', 'crafted', 'smelted', 'fish_caught', 'breeding', 'trades', 'items_sold', 'items_bought', 'challenges_won', 'tasks_completed', 'crates_opened', 'daily_claims', 'passive_job_coins', 'duel_wins', 'duel_losses', 'duel_draws', 'duel_damage'];
  out.statistics = { all_time: pick(object(value.statistics).all_time, metrics), weekly: pick(object(value.statistics).weekly, metrics) };
  const progress = object(value.progress), cosmetics = object(value.cosmetics);
  out.progress = { tasks: (Array.isArray(progress.tasks) ? progress.tasks : []).slice(0, 100).map(task => pick(task, ['id', 'name', 'progress', 'target', 'complete'])), achievements: (Array.isArray(progress.achievements) ? progress.achievements : []).filter(a => typeof a === 'string').slice(0, 500), chapters: (Array.isArray(progress.chapters) ? progress.chapters : []).filter(Number.isSafeInteger).slice(0, 100) };
  out.cosmetics = Object.fromEntries(['prefix', 'color', 'title'].map(type => [type, (Array.isArray(cosmetics[type]) ? cosmetics[type] as unknown[] : []).slice(0, 500).map(entry => pick(entry, ['id', 'display', 'value', 'owned', 'selected']))]));
  return out;
}
async function body(request: Request): Promise<Record<string, unknown>> {
  const raw = await boundedText(request, 512_000);
  return object(JSON.parse(raw));
}
async function boundedText(source: Request | Response, limit: number): Promise<string> {
  if (!source.body) return '';
  const reader = source.body.getReader(), decoder = new TextDecoder();
  let total = 0, out = '';
  try { for (;;) { const chunk = await reader.read(); if (chunk.done) break; total += chunk.value.byteLength; if (total > limit) { await reader.cancel(); throw new Error('Payload too large'); } out += decoder.decode(chunk.value, { stream: true }); } return out + decoder.decode(); }
  finally { reader.releaseLock(); }
}
async function stripe(env: Env, path: string, values?: Record<string, string>, idempotency?: string): Promise<Record<string, unknown>> {
  const key = env.ECONOMYSUITE_STRIPE_KEY || env.STRIPE_SECRET_KEY;
  if (!key) throw new Error('Stripe is not configured');
  const headers: Record<string, string> = { Authorization: `Bearer ${key}`, 'Stripe-Version': '2026-09-30.endive' };
  if (values) headers['Content-Type'] = 'application/x-www-form-urlencoded';
  if (idempotency) headers['Idempotency-Key'] = idempotency;
  const response = await fetch(`https://api.stripe.com/v1/${path}`, { method: values ? 'POST' : 'GET', headers, body: values ? new URLSearchParams(values) : undefined, signal: AbortSignal.timeout(10000) });
  if (!response.ok) throw new Error(`EconomySuite Stripe request failed (${response.status})`);
  return object(JSON.parse(await boundedText(response, 2_000_000)));
}
export function packageFromProduct(value: unknown): Package | null {
  const p = object(value), m = object(p.metadata), price = object(p.default_price), pm = object(price.metadata);
  const amount = integer(pm.es_amount, 1), minor = integer(price.unit_amount, 1);
  if (p.active !== true || m.es_product !== 'economysuite' || m.es_server !== 'pantheon' || m.es_published !== 'true' || price.active !== true || price.currency !== 'czk' || price.type !== 'one_time' || !amount || !minor || !['coins', 'tokens'].includes(s(pm.es_currency)) || !s(price.id)) return null;
  return { id: s(price.id), name: s(p.name), description: s(p.description), currency: pm.es_currency as Currency, amount, price_minor: minor, sort: integer(m.es_sort) ?? 0 };
}
async function catalog(env: Env): Promise<Package[]> {
  const out: Package[] = [];
  let cursor = '';
  for (let page = 0; page < 20; page++) {
    const data = await stripe(env, `products?active=true&limit=100&expand[]=data.default_price${cursor ? `&starting_after=${encodeURIComponent(cursor)}` : ''}`);
    const rows = Array.isArray(data.data) ? data.data : [];
    for (const row of rows) { const pack = packageFromProduct(row); if (pack) out.push(pack); }
    if (!data.has_more || !rows.length) break;
    cursor = s(object(rows.at(-1)).id);
  }
  return out.sort((a, b) => a.sort - b.sort || a.price_minor - b.price_minor);
}
export function targetCurrency(amount: number, paidMinor: number, refundedMinor: number, dispute: string): number {
  if (!Number.isSafeInteger(amount) || amount < 0 || !Number.isSafeInteger(paidMinor) || paidMinor < 1) throw new Error('Invalid order');
  if (dispute && dispute !== 'won' && dispute !== 'warning_closed') return 0;
  const refunded = Math.max(0, Math.min(paidMinor, refundedMinor));
  return amount - Number(BigInt(amount) * BigInt(refunded) / BigInt(paidMinor));
}
async function webhook(request: Request, env: Env, db: D1Database): Promise<Response> {
  if (!env.ECONOMYSUITE_WEBHOOK_SECRET) return error('unavailable', 'Store payments are not configured.', 503);
  const raw = await boundedText(request, 256_000);
  try { await verifySignature(raw, request.headers.get('Stripe-Signature'), env.ECONOMYSUITE_WEBHOOK_SECRET); }
  catch { return error('invalid_signature', 'Invalid webhook signature.', 400); }
  const event = object(JSON.parse(raw)), data = object(object(event.data).object), type = s(event.type), eventId = s(event.id);
  if (!eventId) return error('invalid_event', 'Missing event identifier.');
  if (await db.prepare('SELECT id FROM webhook_events WHERE id=?').bind(eventId).first()) return reply({ received: true });
  let order: Order | null = null;
  if (type.startsWith('checkout.session.')) {
    if (object(data.metadata).purchase_type !== 'economysuite_currency') return reply({ received: true });
    order = await db.prepare('SELECT * FROM store_orders WHERE session_id=?').bind(s(data.id)).first<Order>();
    if (!order) {
      // Recover a session created just before a Worker/network failure prevented
      // its identifier from being saved. Stripe metadata is validated below.
      order = await db.prepare('SELECT * FROM store_orders WHERE id=? AND session_id IS NULL').bind(s(object(data.metadata).order_id)).first<Order>();
      if (order) order.session_id = s(data.id);
    }
  } else if (type.startsWith('charge.') || type.startsWith('refund.')) {
    order = await db.prepare('SELECT * FROM store_orders WHERE payment_intent=?').bind(s(data.payment_intent)).first<Order>();
    // Account-wide Stripe endpoints also receive unrelated product events.
    // A subsequent checkout event reconciles a payment not recorded yet.
    if (!order) return reply({ received: true });
  } else return reply({ received: true });
  if (!order) return error('order_not_ready', 'Order is not available yet. Retry delivery.', 503);
  const session = await stripe(env, `checkout/sessions/${encodeURIComponent(order.session_id!)}?expand[]=line_items`);
  const metadata = object(session.metadata), lines = object(session.line_items), first = object((Array.isArray(lines.data) ? lines.data : [])[0]);
  if (metadata.order_id !== order.id || metadata.purchase_type !== 'economysuite_currency' || metadata.customer_id !== order.customer_id || metadata.player_uuid !== order.uuid || session.currency !== 'czk' || Number(session.amount_total) !== order.price_minor || object(first.price).id !== order.price_id || first.quantity !== 1) return error('order_mismatch', 'Payment does not match the order.', 409);
  const mapped = await db.prepare('UPDATE store_orders SET session_id=? WHERE id=? AND (session_id IS NULL OR session_id=?)').bind(order.session_id, order.id, order.session_id).run();
  if (!mapped.meta.changes) return error('retry', 'Concurrent session mapping. Retry.', 503);
  if (session.payment_status !== 'paid') {
    if (['checkout.session.expired', 'checkout.session.async_payment_failed'].includes(type)) await db.batch([
      db.prepare("UPDATE store_orders SET state='cancelled',updated_at=? WHERE id=? AND paid=0").bind(now(), order.id),
      db.prepare('INSERT OR IGNORE INTO webhook_events(id,processed_at) VALUES(?,?)').bind(eventId, now()),
    ]);
    return reply({ received: true });
  }
  const intentId = s(session.payment_intent), intent = await stripe(env, `payment_intents/${encodeURIComponent(intentId)}?expand[]=latest_charge`), charge = object(intent.latest_charge);
  let disputeId = type.startsWith('charge.dispute.') ? s(data.id) : order.dispute_id;
  let dispute = disputeId ? await stripe(env, `disputes/${encodeURIComponent(disputeId)}`) : null;
  if (charge.disputed === true) {
    const current = await stripe(env, `disputes?payment_intent=${encodeURIComponent(intentId)}&limit=100`);
    const rows = (Array.isArray(current.data) ? current.data : []).map(object);
    dispute = rows.find(row => !['won', 'warning_closed'].includes(s(row.status))) || rows[0] || null;
    if (!dispute || !s(dispute.id)) throw new Error('Disputed payment is not ready for reconciliation');
    disputeId = s(dispute.id);
  }
  const target = targetCurrency(order.currency_amount, order.price_minor, Number(charge.amount_refunded || 0), s(dispute?.status));
  const state = target === 0 ? (dispute && !['won', 'warning_closed'].includes(s(dispute.status)) ? 'disputed' : 'refunded') : target < order.currency_amount ? 'partially_refunded' : 'paid';
  // The optimistic revision prevents concurrent webhook handlers from overwriting
  // each other. All payment state is retrieved from Stripe, rather than trusting
  // event arrival order. Failed comparisons are retried by Stripe.
  const revision = order.revision + 1, timestamp = now(), operation = crypto.randomUUID();
  const changed = await db.batch([
    db.prepare('INSERT INTO bridge_operations(id,uuid,kind,payload,order_id,revision,created_at) SELECT ?,?,?,?,?,?,? FROM store_orders WHERE id=? AND revision=?').bind(operation, order.uuid, 'purchase', JSON.stringify({ order_id: order.id, currency: order.currency_type, target_amount: target, revision }), order.id, revision, timestamp, order.id, order.revision),
    db.prepare('UPDATE store_orders SET paid=1,payment_intent=?,dispute_id=?,target_amount=?,revision=?,state=?,receipt_url=?,updated_at=? WHERE id=? AND revision=?').bind(intentId, disputeId, target, revision, state, s(charge.receipt_url) || null, timestamp, order.id, order.revision),
    db.prepare('INSERT OR IGNORE INTO webhook_events(id,processed_at) SELECT ?,? WHERE EXISTS(SELECT 1 FROM bridge_operations WHERE id=?)').bind(eventId, timestamp, operation),
  ]);
  if (!changed[1].meta.changes) return error('retry', 'Concurrent order update. Retry.', 503);
  return reply({ received: true });
}
async function signedBridge(request: Request, env: Env, db: D1Database): Promise<Record<string, unknown> | null> {
  const timestamp = request.headers.get('X-ES-Time') || '', nonce = request.headers.get('X-ES-Nonce') || '', signature = request.headers.get('X-ES-Signature') || '';
  if (!env.ECONOMYSUITE_BRIDGE_SECRET || !/^\d{10}$/.test(timestamp) || Math.abs(now() - Number(timestamp)) > 120 || !/^[a-f0-9-]{36}$/i.test(nonce)) return null;
  const raw = await boundedText(request, 512_000);
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(env.ECONOMYSUITE_BRIDGE_SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const signed = new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${timestamp}\n${nonce}\n${new URL(request.url).pathname}\n${raw}`)));
  const expected = [...signed].map(b => b.toString(16).padStart(2, '0')).join('');
  if (!timingSafeEqual(signature, expected)) return null;
  const result = await db.prepare('INSERT OR IGNORE INTO bridge_nonces(nonce,expires_at) VALUES(?,?)').bind(nonce, now() + 300).run();
  if (!result.meta.changes) return null;
  return object(JSON.parse(raw));
}
async function bridge(request: Request, env: Env, db: D1Database, path: string): Promise<Response> {
  if (request.method !== 'POST') return error('method_not_allowed', 'POST required.', 405);
  const data = await signedBridge(request, env, db);
  if (!data) return error('forbidden', 'Invalid bridge request.', 403);
  await db.prepare("INSERT INTO bridge_status(server,last_seen) VALUES('pantheon',?) ON CONFLICT(server) DO UPDATE SET last_seen=excluded.last_seen").bind(now()).run();
  if (path.endsWith('/pair/start')) {
    const uuid = s(data.uuid), name = s(data.name);
    if (!UUID.test(uuid) || !/^[A-Za-z0-9_]{1,16}$/.test(name)) return error('invalid_input', 'Invalid player.');
    if (await db.prepare('SELECT uuid FROM player_links WHERE uuid=?').bind(uuid).first()) return error('already_linked', 'This player is already linked.', 409);
    const token = generateToken();
    await db.batch([db.prepare('DELETE FROM pairing_challenges WHERE uuid=?').bind(uuid), db.prepare('INSERT INTO pairing_challenges(token_hash,uuid,name,expires_at) VALUES(?,?,?,?)').bind(await sha256(token), uuid, name, now() + 300)]);
    return reply({ url: `${env.PORTAL_ORIGIN}/economysuite/pair#pair=${token}`, token, expires_at: now() + 300 });
  }
  if (path.endsWith('/pair/confirm')) {
    const hash = await sha256(s(data.token)), row = await db.prepare('SELECT * FROM pairing_challenges WHERE token_hash=? AND uuid=? AND expires_at>? AND confirmed_at IS NULL').bind(hash, s(data.uuid), now()).first<{ uuid: string; name: string; customer_id: string; confirmation_hash: string }>();
    if (!row?.customer_id || !timingSafeEqual(await sha256(s(data.confirmation)), row.confirmation_hash || '')) return error('invalid_confirmation', 'Pairing is missing, expired, or the code is incorrect.');
    try {
      await db.batch([db.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,?)').bind(row.customer_id, row.uuid, row.name, now()), db.prepare('UPDATE pairing_challenges SET confirmed_at=? WHERE token_hash=? AND confirmed_at IS NULL').bind(now(), hash)]);
    } catch { return error('already_linked', 'An account or player is already linked.', 409); }
    return reply({ linked: true });
  }
  if (path.endsWith('/sync')) {
    const snapshots = Array.isArray(data.snapshots) ? data.snapshots.slice(0, 50) : [];
    const statements: D1PreparedStatement[] = [];
    for (const entry of snapshots) {
      const item = object(entry), uuid = s(item.uuid);
      if (!UUID.test(uuid) || !(await db.prepare('SELECT uuid FROM player_links WHERE uuid=?').bind(uuid).first())) continue;
      const payload = JSON.stringify(playerSnapshot(item));
      if (payload.length > 100_000) continue;
      statements.push(db.prepare('INSERT INTO player_snapshots(uuid,payload,synced_at) VALUES(?,?,?) ON CONFLICT(uuid) DO UPDATE SET payload=excluded.payload,synced_at=excluded.synced_at').bind(uuid, payload, now()));
    }
    if (statements.length) await db.batch(statements);
    return reply({ synced: true });
  }
  if (path.endsWith('/poll')) {
    await db.prepare('DELETE FROM bridge_nonces WHERE expires_at<?').bind(now()).run();
    const links = await db.prepare('SELECT uuid,name FROM player_links').all();
    const operations = await db.prepare("SELECT id,uuid,kind,payload FROM bridge_operations WHERE state='pending' ORDER BY created_at,rowid LIMIT 30").all<{ id: string; uuid: string; kind: string; payload: string }>();
    return reply({ links: links.results, operations: operations.results.map(o => ({ ...o, payload: JSON.parse(o.payload) })) });
  }
  if (path.endsWith('/ack')) {
    const op = await db.prepare("SELECT order_id,revision FROM bridge_operations WHERE id=? AND state='pending'").bind(s(data.id)).first<{ order_id: string | null; revision: number }>();
    if (!op) return reply({ acknowledged: true });
    const success = data.success === true, statements = [db.prepare('UPDATE bridge_operations SET state=?,result=?,completed_at=? WHERE id=?').bind(success ? 'complete' : 'failed', s(data.message).slice(0, 300), now(), s(data.id))];
    if (success && op.order_id) statements.push(db.prepare('UPDATE store_orders SET delivered_revision=MAX(delivered_revision,?) WHERE id=?').bind(op.revision, op.order_id));
    await db.batch(statements);
    return reply({ acknowledged: true });
  }
  return error('not_found', 'Not found.', 404);
}
export async function economySuite(request: Request, env: Env, auth: EconomyAuth): Promise<Response> {
  const path = new URL(request.url).pathname, db = env.ECONOMYSUITE_DB;
  if (!db) return error('unavailable', 'The player portal is being configured.', 503);
  if (path === '/api/economysuite/stripe/webhook' && request.method === 'POST') return webhook(request, env, db);
  if (path.startsWith('/api/economysuite/bridge/')) return bridge(request, env, db, path);
  if (path === '/api/economysuite/catalog' && request.method === 'GET') return reply({ packages: await catalog(env), purchases_enabled: env.ECONOMYSUITE_PURCHASES_ENABLED === 'true' });
  const player = await auth.authenticate(request);
  if (!player) return error('not_authenticated', 'Sign in to your player account.', 401);
  if (!player.credential) return error('password_required', 'Set an account password before pairing.', 428);
  if (request.method !== 'GET' && !(await auth.mutation(request))) return error('forbidden', 'Invalid request.', 403);
  if (!(await rateLimit(env.DB, `es:${player.customer.id}`, 60, 90))) return error('rate_limited', 'Please try again shortly.', 429);
  const link = await db.prepare('SELECT * FROM player_links WHERE customer_id=?').bind(player.customer.id).first<Link>();
  if (path === '/api/economysuite/account' && request.method === 'GET') {
    const snapshot = link ? await db.prepare('SELECT payload,synced_at FROM player_snapshots WHERE uuid=?').bind(link.uuid).first<{ payload: string; synced_at: number }>() : null;
    const heartbeat = await db.prepare("SELECT last_seen FROM bridge_status WHERE server='pantheon'").first<{ last_seen: number }>();
    const pending = link ? await db.prepare("SELECT id,kind,state,result FROM bridge_operations WHERE uuid=? AND kind='cosmetic' ORDER BY created_at DESC LIMIT 10").bind(link.uuid).all() : { results: [] };
    return reply({ email: player.customer.email, link, snapshot: snapshot ? JSON.parse(snapshot.payload) : null, synced_at: snapshot?.synced_at ?? null, server_online: Boolean(heartbeat && now() - heartbeat.last_seen < 90), cosmetic_operations: pending.results });
  }
  if (path === '/api/economysuite/orders' && request.method === 'GET') {
    const orders = await db.prepare('SELECT id,player_name,currency_type,currency_amount,price_minor,state,revision,delivered_revision,receipt_url,created_at FROM store_orders WHERE customer_id=? ORDER BY created_at DESC LIMIT 100').bind(player.customer.id).all();
    return reply({ orders: orders.results });
  }
  if (path === '/api/economysuite/leaderboard' && request.method === 'GET') {
    const metric = new URL(request.url).searchParams.get('metric') || 'playtime';
    if (!['playtime', 'blocks_mined', 'tasks_completed', 'duel_wins'].includes(metric)) return error('invalid_input', 'Unknown statistic.');
    const rows = await db.prepare("SELECT l.uuid,l.name,CAST(json_extract(s.payload, ?) AS INTEGER) AS value FROM player_links l JOIN player_snapshots s ON s.uuid=l.uuid WHERE l.leaderboard=1 ORDER BY value DESC,l.name LIMIT 50").bind(`$.statistics.all_time.${metric}`).all();
    return reply({ metric, entries: rows.results });
  }
  const data = request.method === 'POST' ? await body(request) : {};
  if (path === '/api/economysuite/pair/inspect' && request.method === 'POST') {
    const row = await db.prepare('SELECT uuid,name,expires_at FROM pairing_challenges WHERE token_hash=? AND expires_at>? AND confirmed_at IS NULL').bind(await sha256(s(data.token)), now()).first();
    return row ? reply(row) : error('pair_expired', 'Start a new pairing with /web link.', 410);
  }
  if (path === '/api/economysuite/pair/approve' && request.method === 'POST') {
    if (link) return error('already_linked', 'Unlink your current player first.', 409);
    const hash = await sha256(s(data.token)), confirmation = generateToken().slice(0, 8).toUpperCase();
    const result = await db.prepare('UPDATE pairing_challenges SET customer_id=?,confirmation_hash=? WHERE token_hash=? AND expires_at>? AND confirmed_at IS NULL AND customer_id IS NULL').bind(player.customer.id, await sha256(confirmation), hash, now()).run();
    return result.meta.changes ? reply({ confirmation, command: `/web confirm ${confirmation}` }) : error('pair_expired', 'This pairing was already used or expired. Start /web link again.', 410);
  }
  if (path === '/api/economysuite/unlink' && request.method === 'POST') {
    if (!link) return reply({ unlinked: true });
    if (!(await verifyPassword(s(data.password), player.credential.password_hash))) return error('invalid_password', 'The password is incorrect.', 401);
    const abandoned = await db.prepare("SELECT id,session_id FROM store_orders WHERE uuid=? AND state='checkout' AND paid=0 AND created_at<? LIMIT 20").bind(link.uuid, now() - 2400).all<{ id: string; session_id: string | null }>();
    for (const checkout of abandoned.results) {
      if (!checkout.session_id || (await stripe(env, `checkout/sessions/${encodeURIComponent(checkout.session_id)}`)).status === 'expired') {
        await db.prepare("UPDATE store_orders SET state='cancelled',updated_at=? WHERE id=? AND paid=0 AND state='checkout'").bind(now(), checkout.id).run();
      }
    }
    const removed = await db.prepare("DELETE FROM player_links WHERE customer_id=? AND NOT EXISTS(SELECT 1 FROM store_orders WHERE uuid=? AND (state='checkout' OR revision>delivered_revision)) AND NOT EXISTS(SELECT 1 FROM bridge_operations WHERE uuid=? AND state='pending')").bind(player.customer.id, link.uuid, link.uuid).run();
    if (!removed.meta.changes) return error('pending_delivery', 'Resolve outstanding checkouts and deliveries before unlinking.', 409);
    await db.prepare('DELETE FROM pairing_challenges WHERE customer_id=?').bind(player.customer.id).run();
    return reply({ unlinked: true });
  }
  if (!link) return error('pair_required', 'Pair your Minecraft account first.', 409);
  if (path === '/api/economysuite/privacy' && request.method === 'POST') {
    if (typeof data.leaderboard !== 'boolean') return error('invalid_input', 'Choose a privacy preference.');
    await db.prepare('UPDATE player_links SET leaderboard=? WHERE customer_id=?').bind(data.leaderboard ? 1 : 0, player.customer.id).run();
    return reply({ saved: true });
  }
  if (path === '/api/economysuite/cosmetics' && request.method === 'POST') {
    const type = s(data.type), id = s(data.id);
    if (!['prefix', 'color', 'title'].includes(type) || !/^[a-z0-9_-]{0,80}$/.test(id)) return error('invalid_input', 'Invalid cosmetic.');
    const operation = crypto.randomUUID();
    await db.prepare('INSERT INTO bridge_operations(id,uuid,kind,payload,created_at) VALUES(?,?,?,?,?)').bind(operation, link.uuid, 'cosmetic', JSON.stringify({ type, id }), now()).run();
    return reply({ queued: true, operation_id: operation });
  }
  if (path === '/api/economysuite/checkout' && request.method === 'POST') {
    if (env.ECONOMYSUITE_PURCHASES_ENABLED !== 'true') return error('unavailable', 'Purchases are not available yet.', 503);
    const pack = (await catalog(env)).find(p => p.id === s(data.price_id));
    if (!pack) return error('invalid_package', 'This package is no longer available.');
    const id = crypto.randomUUID(), timestamp = now();
    await db.prepare('INSERT INTO store_orders(id,customer_id,uuid,player_name,price_id,currency_type,currency_amount,price_minor,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)').bind(id, player.customer.id, link.uuid, link.name, pack.id, pack.currency, pack.amount, pack.price_minor, timestamp, timestamp).run();
    try {
      const checkout = await stripe(env, 'checkout/sessions', { mode: 'payment', customer_email: player.customer.email, 'line_items[0][price]': pack.id, 'line_items[0][quantity]': '1', 'metadata[purchase_type]': 'economysuite_currency', 'metadata[order_id]': id, 'metadata[customer_id]': player.customer.id, 'metadata[player_uuid]': link.uuid, 'payment_intent_data[metadata][purchase_type]': 'economysuite_currency', success_url: `${env.PORTAL_ORIGIN}/economysuite/purchases?order=${id}`, cancel_url: `${env.PORTAL_ORIGIN}/economysuite/store`, expires_at: String(timestamp + 1800), integration_identifier: `economysuite_${generateToken().replace(/[^a-z]/gi, '').slice(0, 8).padEnd(8, 'x')}` }, id);
      const checkoutUrl = s(checkout.url);
      if (!checkoutUrl.startsWith('https://checkout.stripe.com/')) throw new Error('Invalid checkout URL');
      await db.prepare('UPDATE store_orders SET session_id=? WHERE id=?').bind(s(checkout.id), id).run();
      return reply({ url: checkoutUrl, order_id: id });
    } catch (failure) {
      await db.prepare("UPDATE store_orders SET state='cancelled' WHERE id=?").bind(id).run();
      throw failure;
    }
  }
  return error('not_found', 'Not found.', 404);
}
