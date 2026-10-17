import { describe, it, expect } from 'vitest';
import { rewardDay, nextRewardReset, randomReward } from './economysuite-daily';

const seconds = (date: string) => Date.parse(date) / 1000;
describe('Prague daily reward clock', () => {
  it('resets at Prague midnight rather than UTC midnight', () => {
    expect(rewardDay(seconds('2026-10-17T21:59:59Z'))).toBe('2026-10-17');
    expect(rewardDay(seconds('2026-10-17T22:00:00Z'))).toBe('2026-10-18');
    expect(nextRewardReset(seconds('2026-10-17T21:59:59Z'))).toBe(seconds('2026-10-17T22:00:00Z'));
  });
  it('handles both DST transitions, including 23-hour and 25-hour days', () => {
    expect(nextRewardReset(seconds('2026-03-28T23:00:00Z'))).toBe(seconds('2026-03-29T22:00:00Z'));
    expect(nextRewardReset(seconds('2026-10-24T22:00:00Z'))).toBe(seconds('2026-10-25T23:00:00Z'));
  });
  it('only generates integer rewards between one and five', () => {
    const values = new Set<number>();
    for (let i=0;i<200;i++) { const value=randomReward(); expect(Number.isInteger(value)).toBe(true); expect(value).toBeGreaterThanOrEqual(1); expect(value).toBeLessThanOrEqual(5); values.add(value); }
    expect(values.size).toBe(5);
  });
});
