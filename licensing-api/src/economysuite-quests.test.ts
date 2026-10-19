import { describe, expect, it } from 'vitest';
import { questProgress } from './economysuite-quests';

describe('current daily and weekly quest snapshot', () => {
  const row = { id: 'mine', name: '&eMine stone', progress: 42, target: 100, complete: false, reward_coins: 50, points: 1 };
  it('discards retired task batches from both old stored and newly submitted snapshots', () => {
    expect(questProgress({ tasks: [row], daily: [row] })).toEqual({ tasks_version: 0, daily: [], weekly: [], cycles: { daily: '', weekly: '' } });
    expect(questProgress(null).daily).toEqual([]);
  });
  it('keeps period identity, progress, completion and rewards without private fields', () => {
    const result = questProgress({ tasks_version: 2, daily: [{ ...row, private_field: 'secret' }], weekly: [{ ...row, id: 'weekly', complete: true }], cycles: { daily: '2026-10-20', weekly: '2026-10-19' } });
    expect(result.daily).toEqual([row]); expect(result.weekly[0].complete).toBe(true); expect(result.cycles.daily).toBe('2026-10-20'); expect(result).not.toHaveProperty('tasks');
    expect(questProgress(result)).toEqual(result);
  });
  it('bounds arrays and values and rejects malformed periods and rows', () => {
    const result = questProgress({ tasks_version: 2, daily: [{ ...row, progress: 999, reward_coins: -1, complete: 'yes' }, { id: 'bad', target: 0 }, null], weekly: Array(105).fill(row), cycles: { daily: '<script>', weekly: '2026-10-19' } });
    expect(result.daily).toEqual([{ ...row, progress: 100, reward_coins: 0, complete: false }]); expect(result.weekly).toHaveLength(100); expect(result.cycles.daily).toBe('');
  });
});
