/// <reference types="node" />
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { build } from 'esbuild';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';
import { readFileSync, readdirSync } from 'node:fs';
import { BridgeRequestQueue } from './economysuite-bridge-coordinator';
import worker from './index';
import type { Env } from './config';

describe('bounded bridge scheduling', () => {
  afterEach(() => vi.useRealTimers());

  it('serializes polls in arrival order and recovers after a handler throws', async () => {
    const queue = new BridgeRequestQueue();
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    const events: string[] = [];
    const first = queue.run(async () => { events.push('first'); await gate; events.push('first done'); return new Response(); });
    const second = queue.run(async () => { events.push('second'); throw new Error('database failure'); });
    const failed = expect(second).rejects.toThrow('database failure');
    const third = queue.run(async () => { events.push('third'); return new Response(); });
    expect(events).toEqual(['first']);
    release();
    await first; await failed; await third;
    expect(events).toEqual(['first', 'first done', 'second', 'third']);
    expect((await queue.run(async () => new Response())).status).toBe(200);
  });

  it('rejects overflow and removes expired waiters without running them later', async () => {
    vi.useFakeTimers();
    const queue = new BridgeRequestQueue(1, 50);
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    const first = queue.run(async () => { await gate; return new Response(); });
    const expiredTask = vi.fn(async () => new Response());
    const waiting = queue.run(expiredTask);
    const overflow = await queue.run(async () => new Response());
    expect(overflow.status).toBe(503);
    expect(overflow.headers.get('Retry-After')).toBe('10');
    await vi.advanceTimersByTimeAsync(51);
    expect((await waiting).status).toBe(503);
    const recovered = queue.run(async () => new Response('recovered'));
    release(); await first;
    expect(await (await recovered).text()).toBe('recovered');
    expect(expiredTask).not.toHaveBeenCalled();
  });
});

describe('bundled Worker and SQLite Durable Object with real D1', () => {
  let runtime: Miniflare;
  let db: D1Database;
  const secret = 'local-coordinator-fixture-secret';
  const origin = 'https://account.pantheon.tomaspisar.cz';
  const main = '/api/economysuite/bridge/poll';
  const staff = '/api/economysuite/bridge/staff/poll';
  const sync = '/api/economysuite/bridge/sync';
  const uuid = '11111111-1111-4111-8111-111111111111';

  beforeAll(async () => {
    const bundle = await build({ entryPoints: ['src/index.ts'], bundle: true, format: 'esm', platform: 'neutral', target: 'es2022', write: false });
    runtime = new Miniflare(convertV4MiniflareOptions({
      modules: true, script: bundle.outputFiles[0].text, compatibilityDate: '2026-08-01',
      d1Databases: ['DB', 'ECONOMYSUITE_DB'],
      durableObjects: { ECONOMYSUITE_BRIDGE_COORDINATOR: { className: 'EconomyBridgeCoordinator', useSQLite: true } },
      bindings: { ENVIRONMENT: 'production', ECONOMYSUITE_BRIDGE_SECRET: secret, PORTAL_ORIGIN: 'https://account.ljr.tomaspisar.cz', ECONOMYSUITE_PORTAL_ORIGIN: origin },
    }));
    db = await runtime.getD1Database('ECONOMYSUITE_DB') as unknown as D1Database;
    for (const file of readdirSync('economysuite-migrations').filter(name => name.endsWith('.sql')).sort()) {
      const sql = readFileSync('economysuite-migrations/' + file, 'utf8').replace(/--[^\n]*/g, '').split(/;(?!\s*END\b)/i).map(s => s.replace(/\r?\n/g, ' ').trim()).filter(Boolean).join(';\n') + ';';
      await db.exec(sql);
    }
  }, 30000);
  afterAll(async () => { await runtime?.dispose(); });
  beforeEach(async () => {
    await db.batch(['bridge_status', 'bridge_nonces', 'bridge_operations'].map(table => db.prepare('DELETE FROM ' + table)));
    await db.prepare("UPDATE staff_control SET revision=1,applied_revision=0,runtime='{}',economy_monitor_generated_at=0 WHERE id=1").run();
  });

  async function signed(path: string, payload: unknown, options: { nonce?: string; time?: number; host?: string } = {}) {
    const raw = JSON.stringify(payload), nonce = options.nonce ?? crypto.randomUUID();
    const timestamp = String(options.time ?? Math.floor(Date.now() / 1000));
    const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const signature = Buffer.from(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${timestamp}\n${nonce}\n${path}\n${raw}`))).toString('hex');
    return { url: (options.host ?? origin) + path, init: { method: 'POST', body: raw, headers: { 'X-ES-Time': timestamp, 'X-ES-Nonce': nonce, 'X-ES-Signature': signature } } };
  }
  async function poll(path: string, payload: unknown, options: Parameters<typeof signed>[2] = {}) {
    const request = await signed(path, payload, options);
    return runtime.dispatchFetch(request.url, request.init);
  }

  it('routes both split polls, preserves a large runtime and advances the heartbeat', async () => {
    const diagnostic = 'large signed payload '.repeat(8000);
    const response = await poll(staff, { staff_revision: 1, staff_runtime: { ready: true, instance: uuid, diagnostic } });
    expect(response.status).toBe(200);
    expect(response.headers.get('X-ES-Bridge-Execution')).toBe('coordinator-v1');
    const saved = await db.prepare('SELECT runtime FROM staff_control WHERE id=1').first<string>('runtime');
    expect(JSON.parse(saved!).diagnostic).toBe(diagnostic);
    const heartbeat = await poll(main, { bridge_version: 2, staff_version: 1, staff_external_version: 1 });
    expect(heartbeat.status).toBe(200);
    expect(heartbeat.headers.get('X-ES-Bridge-Execution')).toBe('coordinator-v1');
    expect((await heartbeat.json() as { staff_external_version: number }).staff_external_version).toBe(1);
    expect(await db.prepare('SELECT runtime FROM staff_control WHERE id=1').first('runtime')).toBe(saved);
    expect(await db.prepare("SELECT last_seen FROM bridge_status WHERE server='pantheon'").first<number>('last_seen')).toBeGreaterThan(Math.floor(Date.now() / 1000) - 10);
  });

  it('preserves allowlisted player snapshots and explicit refreshes through the coordinator', async () => {
    await db.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,?)').bind('sync-fixture', uuid, 'Fixture', 1).run();
    try {
      const payload = { snapshots: [{ uuid, coins: 42, tokens: 7, private_field: 'omit', progress: { achievements: ['fixture'] } }] };
      const response = await poll(sync, payload);
      expect(response.status).toBe(200);
      expect(response.headers.get('X-ES-Bridge-Execution')).toBe('coordinator-v1');
      const row = await db.prepare('SELECT payload,synced_at FROM player_snapshots WHERE uuid=?').bind(uuid).first<{ payload: string; synced_at: number }>();
      expect(JSON.parse(row!.payload)).toMatchObject({ uuid, coins: 42, tokens: 7 });
      expect(JSON.parse(row!.payload)).not.toHaveProperty('private_field');
      await db.prepare('UPDATE player_snapshots SET synced_at=1 WHERE uuid=?').bind(uuid).run();
      expect((await poll(sync, { ...payload, force: true })).status).toBe(200);
      expect(await db.prepare('SELECT synced_at FROM player_snapshots WHERE uuid=?').bind(uuid).first<number>('synced_at')).toBeGreaterThan(1);
    } finally {
      await db.prepare('DELETE FROM player_snapshots WHERE uuid=?').bind(uuid).run();
      await db.prepare('DELETE FROM player_links WHERE uuid=?').bind(uuid).run();
    }
  });

  it.each([main, staff, sync])('rejects unsigned, stale, tampered and replayed requests on %s', async path => {
    expect((await runtime.dispatchFetch(origin + path, { method: 'POST', body: '{}' })).status).toBe(403);
    expect((await poll(path, {}, { time: Math.floor(Date.now() / 1000) - 180 })).status).toBe(403);
    const request = await signed(path, {});
    expect((await runtime.dispatchFetch(request.url, { ...request.init, body: '{"tampered":true}' })).status).toBe(403);
    const nonce = crypto.randomUUID();
    expect((await poll(path, { bridge_version: 2 }, { nonce })).status).toBe(200);
    expect((await poll(path, { bridge_version: 2 }, { nonce })).status).toBe(403);
  });

  it('keeps backoff and does not consume the rejected nonce', async () => {
    expect((await poll(main, { bridge_version: 2 })).status).toBe(200);
    const nonce = crypto.randomUUID();
    const response = await poll(main, { bridge_version: 2 }, { nonce });
    expect(response.status).toBe(429);
    expect(response.headers.get('Retry-After')).toBe('10');
    expect(await db.prepare('SELECT nonce FROM bridge_nonces WHERE nonce=?').bind(nonce).first()).toBeNull();
  });

  it('serializes simultaneous main polls and rejects simultaneous nonce replays', async () => {
    const concurrent = await Promise.all([poll(main, { bridge_version: 2 }), poll(main, { bridge_version: 2 })]);
    expect(concurrent.map(r => r.status).sort()).toEqual([200, 429]);
    const nonce = crypto.randomUUID();
    const replay = await Promise.all([poll(staff, {}, { nonce }), poll(staff, {}, { nonce })]);
    expect(replay.map(r => r.status).sort()).toEqual([200, 403]);
  });

  it('redelivers pending operations until the existing signed acknowledgment confirms them', async () => {
    const id = crypto.randomUUID();
    await db.prepare("INSERT INTO bridge_operations(id,uuid,kind,payload,created_at) VALUES(?,?,'refresh','{}',?)").bind(id, uuid, Math.floor(Date.now() / 1000)).run();
    for (let i = 0; i < 2; i++) {
      await db.prepare("DELETE FROM bridge_status WHERE server='pantheon'").run();
      const response = await poll(main, { bridge_version: 2 });
      expect(response.status).toBe(200);
      expect((await response.json() as { operations: { id: string }[] }).operations.map(op => op.id)).toContain(id);
      expect(await db.prepare('SELECT state FROM bridge_operations WHERE id=?').bind(id).first('state')).toBe('pending');
    }
    const ack = await poll('/api/economysuite/bridge/ack', { id, success: true, message: 'fixture applied' });
    expect(ack.status).toBe(200);
    expect(ack.headers.has('X-ES-Bridge-Execution')).toBe(false);
    expect(await db.prepare('SELECT state FROM bridge_operations WHERE id=?').bind(id).first('state')).toBe('complete');
    await db.prepare("DELETE FROM bridge_status WHERE server='pantheon'").run();
    expect((await (await poll(main, { bridge_version: 2 })).json() as { operations: unknown[] }).operations).toEqual([]);
  });

  it('keeps host, method, OPTIONS and non-poll routing boundaries', async () => {
    expect((await poll(staff, {}, { host: 'https://account.ljr.tomaspisar.cz' })).status).toBe(404);
    expect((await poll(staff, {}, { host: 'https://minecraft.tomaspisar.cz' })).status).toBe(200);
    expect((await runtime.dispatchFetch(origin + main)).status).toBe(405);
    expect((await runtime.dispatchFetch(origin + main, { method: 'OPTIONS' })).status).toBe(204);
    const health = await runtime.dispatchFetch('https://api.tomaspisar.cz/health');
    expect(health.status).toBe(200);
    expect(health.headers.has('X-ES-Bridge-Execution')).toBe(false);
    const ns = await runtime.getDurableObjectNamespace('ECONOMYSUITE_BRIDGE_COORDINATOR');
    const stub = ns.getByName('pantheon');
    expect((await stub.fetch(origin + '/api/economysuite/bridge/ack', { method: 'POST' })).status).toBe(404);
    expect((await stub.fetch(origin + main)).status).toBe(405);
  });

  it('fails closed when the production coordinator binding is missing', async () => {
    const env = { ENVIRONMENT: 'production', ECONOMYSUITE_DB: db, PORTAL_ORIGIN: origin } as Env;
    const response = await worker.fetch(new Request(origin + main, { method: 'POST', body: '{}' }), env);
    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({ error: 'bridge_unavailable' });
  });
});
