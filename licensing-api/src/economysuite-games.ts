import type { Env } from './config';

export const RULES_VERSION = 'es-games-1';
export const SAFE = Number.MAX_SAFE_INTEGER;
export const TABLES = {
  coin: [{ probability: 50, factor: 19 }, { probability: 50, factor: 0 }],
  dice10: [{ probability: 10, factor: 95 }, { probability: 90, factor: 0 }],
  dice25: [{ probability: 25, factor: 38 }, { probability: 75, factor: 0 }],
  dice50: [{ probability: 50, factor: 19 }, { probability: 50, factor: 0 }],
  wheel: [{ probability: 5, factor: 0 }, { probability: 20, factor: 5 }, { probability: 20, factor: 8 }, { probability: 25, factor: 10 }, { probability: 20, factor: 12 }, { probability: 10, factor: 20 }],
};
export interface RoundInput { game: string; currency: string; stake: number; choice: string; rules_version: string; idempotency_key: string }
export interface Round extends RoundInput { id: string; customer_id: string; uuid: string; state: string; created_at: number; expires_at: number; result: string | null; payout: number | null; net: number | null }
const reply = (data: unknown, status = 200) => Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } });
const fail = (error: string, message: string, status = 409) => reply({ error, message }, status);
export function tableFor(game: string, choice: string) {
  if (game === 'coin' && ['heads', 'tails'].includes(choice)) return TABLES.coin;
  if (game === 'dice' && ['10', '25', '50'].includes(choice)) return TABLES[`dice${choice}` as 'dice10' | 'dice25' | 'dice50'];
  if (game === 'wheel' && choice === '') return TABLES.wheel;
  return null;
}
export function maxStake(game: string, choice: string): number {
  const table = tableFor(game, choice);
  return table ? Number(BigInt(SAFE) / BigInt(Math.max(...table.map(x => x.factor))) ) * 10 : 0;
}
export function validInput(data: Record<string, unknown>): data is Record<string, unknown> & RoundInput {
  return typeof data.game === 'string' && typeof data.choice === 'string' && typeof data.currency === 'string' && ['coins', 'tokens'].includes(data.currency) &&
    typeof data.stake === 'number' && Number.isSafeInteger(data.stake) && data.stake >= (data.currency === 'coins' ? 100 : 10) && data.stake % 10 === 0 && data.stake <= maxStake(data.game, data.choice) &&
    data.rules_version === RULES_VERSION && typeof data.idempotency_key === 'string' && /^[A-Za-z0-9_-]{16,100}$/.test(data.idempotency_key);
}
export function outcome(game: string, choice: string, roll: number): { outcome: string; factor: number } | null {
  if (!Number.isInteger(roll) || roll < 0 || roll >= 100) return null;
  const table = tableFor(game, choice); if (!table) return null;
  if (game === 'coin') return { outcome: roll < 50 ? 'heads' : 'tails', factor: (roll < 50 ? 'heads' : 'tails') === choice ? 19 : 0 };
  let end = 0;
  for (let i = 0; i < table.length; i++) { end += table[i].probability; if (roll < end) return { outcome: game === 'wheel' ? String(i) : i === 0 ? 'win' : 'lose', factor: table[i].factor }; }
  return null;
}
export function gamesEnabled(env: Env): boolean {
  if (env.ECONOMYSUITE_GAMES_ENABLED !== 'true') return false;
  if (env.ENVIRONMENT === 'production') return env.PORTAL_ORIGIN === 'https://minecraft.tomaspisar.cz';
  return ['development', 'staging', 'test'].includes(env.ENVIRONMENT) && !['https://account.tomaspisar.cz', 'https://minecraft.tomaspisar.cz', 'https://ljr.tomaspisar.cz'].includes(env.PORTAL_ORIGIN);
}
export async function gamesRoute(request: Request, env: Env, db: D1Database, customer: string, uuid: string | null, data: Record<string, unknown>): Promise<Response> {
  const url = new URL(request.url), path = url.pathname;
  if (path.endsWith('/config') && request.method === 'GET') {
    const bridge = await db.prepare("SELECT last_seen,games_version,games_enabled FROM bridge_status WHERE server='pantheon'").first<{ last_seen: number; games_version: string | null; games_enabled: number }>();
    return reply({ enabled: gamesEnabled(env), server_enabled: bridge?.games_enabled === 1, supported: bridge?.games_version === RULES_VERSION, connected: !!bridge && bridge.last_seen > Math.floor(Date.now() / 1000) - 20, rules_version: RULES_VERSION, tables: TABLES, minimum: { coins: 100, tokens: 10 }, step: 10, cooldown: 5 });
  }
  if (request.method === 'GET') {
    const id = path.match(/\/rounds\/([a-f0-9-]{36})$/)?.[1];
    if (id) { const round = await db.prepare('SELECT * FROM game_rounds WHERE id=? AND customer_id=?').bind(id, customer).first(); return round ? reply({ round }) : fail('not_found', 'Round not found.', 404); }
    if (!path.endsWith('/rounds')) return fail('not_found', 'Not found.', 404);
    const filters: Record<string, string> = { all: '', wins: ' AND net>0', losses: ' AND net<0', returned: ' AND net=0' };
    const filter = url.searchParams.get('filter') || 'all';
    if (!(filter in filters)) return fail('invalid_input', 'Unknown filter.', 422);
    const before = Number(url.searchParams.get('before') || SAFE);
    if (!Number.isSafeInteger(before) || before < 0) return fail('invalid_input', 'Invalid cursor.', 422);
    const rounds = await db.prepare(`SELECT rowid AS cursor,* FROM game_rounds WHERE customer_id=? AND rowid<?${filters[filter]} ORDER BY rowid DESC LIMIT 100`).bind(customer, before).all();
    return reply({ rounds: rounds.results });
  }
  if (request.method !== 'POST' || !path.endsWith('/rounds')) return fail('method_not_allowed', 'Unsupported method.', 405);
  if (!uuid) return fail('pair_required', 'Pair your Minecraft account first.');
  if (!validInput(data)) return fail('invalid_input', 'Invalid game, choice, currency, stake or rules version.', 422);
  const existing = await db.prepare('SELECT * FROM game_rounds WHERE customer_id=? AND idempotency_key=?').bind(customer, data.idempotency_key).first<Round>();
  if (existing) {
    if (['game', 'currency', 'stake', 'choice', 'rules_version'].some(key => existing[key as keyof Round] !== data[key])) return fail('idempotency_conflict', 'This key belongs to a different bet.');
    return reply({ round: existing });
  }
  if (!gamesEnabled(env)) return fail('games_disabled', 'Games are disabled.', 503);
  const bridge = await db.prepare("SELECT last_seen,games_version,games_enabled FROM bridge_status WHERE server='pantheon'").first<{ last_seen: number; games_version: string | null; games_enabled: number }>();
  const timestamp = Math.floor(Date.now() / 1000);
  if (!bridge || bridge.last_seen <= timestamp - 20) return fail('server_offline', 'The server is disconnected.', 503);
  if (bridge.games_version !== RULES_VERSION) return fail('unsupported_plugin', 'The server does not support these rules.', 503);
  if (bridge.games_enabled !== 1) return fail('server_games_disabled', 'Games are disabled on the server.', 503);
  const id = crypto.randomUUID(), payload = { ...data, expires_at: timestamp + 30, created_at: timestamp };
  try {
    await db.batch([
      db.prepare('INSERT INTO game_rounds(id,customer_id,uuid,idempotency_key,game,currency,stake,choice,rules_version,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)').bind(id, customer, uuid, data.idempotency_key, data.game, data.currency, data.stake, data.choice, data.rules_version, timestamp, timestamp + 30),
      db.prepare("INSERT INTO bridge_operations(id,uuid,kind,payload,created_at) VALUES(?,?,'game_round',?,?)").bind(id, uuid, JSON.stringify(payload), timestamp),
    ]);
  } catch (failure) {
    // Concurrent retry may have committed the same key while this request waited.
    const raced = await db.prepare('SELECT * FROM game_rounds WHERE customer_id=? AND idempotency_key=?').bind(customer, data.idempotency_key).first<Round>();
    if (raced && ['game','currency','stake','choice','rules_version'].every(k => raced[k as keyof Round] === data[k])) return reply({ round: raced });
    if (raced) return fail('idempotency_conflict', 'This key belongs to a different bet.');
    if (await db.prepare('SELECT id FROM game_rounds WHERE uuid=? AND (state=\'pending\' OR created_at>?)').bind(uuid, timestamp - 5).first()) return fail('round_busy', 'Wait for your current round and five seconds between bets.');
    throw failure;
  }
  return reply({ round: await db.prepare('SELECT * FROM game_rounds WHERE id=?').bind(id).first() }, 202);
}
export async function gameAcknowledgment(db: D1Database, data: Record<string, unknown>): Promise<Response | null> {
  const round = await db.prepare('SELECT * FROM game_rounds WHERE id=?').bind(String(data.id || '')).first<Round>();
  if (!round) return null;
  if (round.state !== 'pending') return reply({ acknowledged: true });
  const result = data.game_result as Record<string, unknown> | undefined;
  if (!result || result.rules_version !== round.rules_version) return fail('invalid_result', 'Missing structured result.', 422);
  const success = result.state === 'complete';
  if (success) {
    const expected = typeof result.roll === 'number' ? outcome(round.game, round.choice, result.roll) : null;
    const payout = expected ? Number(BigInt(round.stake / 10) * BigInt(expected.factor)) : -1;
    if (!expected || expected.outcome !== result.outcome || payout !== result.payout || result.net !== payout - round.stake || !Number.isSafeInteger(result.balance) || Number(result.balance) < 0) return fail('invalid_result', 'Inconsistent game result.', 422);
  } else if (result.state !== 'rejected' || typeof result.error !== 'string' || !['disabled','expired','insufficient_funds','debt','cooldown','unsafe_balance','invalid_input'].includes(result.error)) return fail('invalid_result', 'Invalid rejection.', 422);
  await db.batch([
    db.prepare("UPDATE game_rounds SET state=?,result=?,payout=?,net=?,completed_at=? WHERE id=? AND state='pending'").bind(success ? 'complete' : 'rejected', JSON.stringify(result), success ? result.payout : null, success ? result.net : null, Math.floor(Date.now() / 1000), round.id),
    db.prepare("UPDATE bridge_operations SET state='complete',result=?,completed_at=? WHERE id=? AND state='pending'").bind(JSON.stringify(result), Math.floor(Date.now() / 1000), round.id),
  ]);
  return reply({ acknowledged: true });
}
