const test = require('node:test');
const assert = require('node:assert/strict');
const Core = require('../tomaspisar.cz/assets/js/pages/relaylab-core.js');

const swimmer = (id, performances) => ({ id, firstName: `Swimmer ${id}`, lastName: '', performances });
const perf = (stroke, timeMs, extra = {}) => ({ stroke, distance: 50, poolLength: 25, timeMs, date: '2026-06-01', relayPart: false, ...extra });
const complete = (id, offset = 0) => swimmer(id, [perf('backstroke', 30000 + offset), perf('breaststroke', 32000 + offset), perf('butterfly', 31000 + offset), perf('freestyle', 28000 + offset)]);

test('selects the fastest exact pool, distance, and period result', () => {
  const swimmerData = swimmer(1, [perf('backstroke', 31000), perf('backstroke', 30000), perf('backstroke', 25000, { poolLength: 50 }), perf('backstroke', 29000, { date: '2024-01-01' })]);
  const selected = Core.selectBestPerformance(swimmerData.performances, 'backstroke', { distance: 50, poolLength: 25, period: 'all' });
  assert.equal(selected.timeMs, 29000);
});

test('excludes relay splits unless explicitly enabled', () => {
  const performances = [perf('freestyle', 26000), perf('freestyle', 24500, { relayPart: true })];
  assert.equal(Core.selectBestPerformance(performances, 'freestyle', { distance: 50, poolLength: 25, period: 'all' }).timeMs, 26000);
  assert.equal(Core.selectBestPerformance(performances, 'freestyle', { distance: 50, poolLength: 25, period: 'all', includeRelaySplits: true }).timeMs, 24500);
});

test('returns the best unique-swimmer assignment and two alternatives', () => {
  const outcome = Core.optimize([complete(1), complete(2, 1000), complete(3, 2000), complete(4, 3000), complete(5, 4000)], { distance: 50, poolLength: 25, period: 'all' });
  assert.equal(outcome.results.length, 3);
  assert.equal(outcome.results[0].totalMs, 127000);
  assert.equal(new Set(outcome.results[0].legs.map((leg) => leg.swimmer.id)).size, 4);
  assert.equal(new Set(outcome.results.map((result) => result.signature)).size, 3);
  assert.ok(outcome.results[1].totalMs >= outcome.results[0].totalMs);
});

test('manual times fill a missing official stroke', () => {
  const outcome = Core.optimize([complete(1), complete(2), complete(3), swimmer(4, [perf('backstroke', 30000), perf('breaststroke', 32000), perf('freestyle', 28000)])], { distance: 50, poolLength: 25, period: 'all', manualTimes: { 4: { butterfly: 29000 } } });
  assert.equal(outcome.results.length, 3);
  const manualLeg = outcome.results.flatMap((result) => result.legs).find((leg) => leg.performance.source === 'manual');
  assert.ok(manualLeg);
});
