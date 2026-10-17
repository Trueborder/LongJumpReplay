/** One Prague calendar-day reward per Minecraft UUID, independent of purchases and ranks. */
export function rewardDay(timestamp: number): string {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Prague', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(timestamp * 1000));
  const part = (name: string) => parts.find(p => p.type === name)!.value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}
export function nextRewardReset(timestamp: number): number {
  const day = rewardDay(timestamp);
  let low = Math.floor(timestamp), high = low + 90_000;
  while (low + 1 < high) { const middle = Math.floor((low + high) / 2); if (rewardDay(middle) === day) low = middle; else high = middle; }
  return high;
}
export function randomReward(): number {
  const value = new Uint32Array(1);
  do { crypto.getRandomValues(value); } while (value[0] === 0xffffffff);
  return value[0] % 5 + 1;
}
interface Claim { day: string; tokens: number; state: string }
export async function dailyStatus(db: D1Database, uuid: string, timestamp: number) {
  const day = rewardDay(timestamp);
  const claim = await db.prepare('SELECT r.day,r.tokens,o.state FROM web_daily_rewards r JOIN bridge_operations o ON o.id=r.operation_id WHERE r.uuid=? AND r.day=?').bind(uuid, day).first<Claim>();
  return { day, available: !claim, amount: claim?.tokens ?? null, status: !claim ? 'available' : claim.state === 'complete' ? 'delivered' : claim.state === 'failed' ? 'failed' : 'pending', minimum: 1, maximum: 5, next_reset_at: nextRewardReset(timestamp) };
}
export async function claimDaily(db: D1Database, uuid: string, customer: string, timestamp: number) {
  const day = rewardDay(timestamp), id = `web-daily:${uuid}:${day}`, candidate = crypto.randomUUID();
  // A random operation candidate ties insertion of the outbox to the winning INSERT.
  // Concurrent requests cannot replace the first amount or produce a second operation.
  await db.batch([
    db.prepare('INSERT OR IGNORE INTO web_daily_rewards(uuid,day,customer_id,tokens,operation_id,claimed_at) VALUES(?,?,?,?,?,?)').bind(uuid, day, customer, randomReward(), candidate, timestamp),
    db.prepare("INSERT INTO bridge_operations(id,uuid,kind,payload,created_at) SELECT operation_id,uuid,'web_daily',json_object('claim_id',?,'day',day,'tokens',tokens),claimed_at FROM web_daily_rewards WHERE operation_id=?").bind(id, candidate),
  ]);
  return dailyStatus(db, uuid, timestamp);
}
