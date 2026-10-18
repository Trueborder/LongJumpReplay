/** Product metadata is operator-controlled, never supplied by the browser. */
export const RANKS = { vip: { name: 'VIP', minor: 3900 }, vipplus: { name: 'VIP+', minor: 6900 }, mvp: { name: 'MVP', minor: 9900 } } as const;
export const RANK_WEEK_SECONDS = 604800;
export type RankId = keyof typeof RANKS;
export function rankProduct(metadata: Record<string, unknown>, price: Record<string, unknown>): RankId | null {
  const id = String(metadata.es_rank || '') as RankId;
  return metadata.es_kind === 'rank' && Object.hasOwn(RANKS, id)
    && Number(price.unit_amount) === RANKS[id].minor
    && Number((price.metadata as Record<string, unknown> | undefined)?.es_duration_seconds) === RANK_WEEK_SECONDS ? id : null;
}
export function rankDelivery(order: { id: string; rank_id?: string | null }, paidAt: number, effectiveAt: number, seconds: number, revision: number) {
  if (!order.rank_id || !Object.hasOwn(RANKS, order.rank_id) || !Number.isSafeInteger(paidAt) || paidAt < 1 || !Number.isSafeInteger(paidAt * 1000) || !Number.isSafeInteger(effectiveAt) || effectiveAt < paidAt || !Number.isSafeInteger(effectiveAt * 1000) || !Number.isSafeInteger(revision) || revision < 1 || !Number.isSafeInteger(seconds) || seconds < 0 || seconds > RANK_WEEK_SECONDS) throw new Error('Invalid rank delivery');
  return { order_id: order.id, rank: order.rank_id, paid_at: paidAt * 1000, effective_at: effectiveAt * 1000, duration_seconds: seconds, revision };
}
