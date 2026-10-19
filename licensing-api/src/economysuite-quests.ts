/** The plugin owns quest definitions, cycle keys, progress and rewards. No web grants. */
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const amount = (value: unknown) => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : 0;
function quests(value: unknown) {
  return (Array.isArray(value) ? value : []).slice(0, 100).flatMap(raw => {
    const row = object(raw), target = amount(row.target);
    if (typeof row.id !== 'string' || !row.id || row.id.length > 128 || !target) return [];
    return [{ id: row.id, name: typeof row.name === 'string' ? row.name.slice(0, 256) : row.id, progress: Math.min(target, amount(row.progress)), target, complete: row.complete === true, reward_coins: amount(row.reward_coins), points: amount(row.points) }];
  });
}
export function questProgress(value: unknown) {
  const progress = object(value), cycles = object(progress.cycles);
  const current = progress.tasks_version === 2;
  const cycle = (key: string) => current && typeof cycles[key] === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(cycles[key]) ? cycles[key] : '';
  return { tasks_version: current ? 2 : 0, daily: current ? quests(progress.daily) : [], weekly: current ? quests(progress.weekly) : [], cycles: { daily: cycle('daily'), weekly: cycle('weekly') } };
}
