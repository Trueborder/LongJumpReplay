(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.RelayLabCore = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const STROKES = [
    { key: 'backstroke', code: 'Z', label: 'Backstroke', labelCs: 'Znak' },
    { key: 'breaststroke', code: 'P', label: 'Breaststroke', labelCs: 'Prsa' },
    { key: 'butterfly', code: 'M', label: 'Butterfly', labelCs: 'Motýlek' },
    { key: 'freestyle', code: 'K', label: 'Freestyle', labelCs: 'Volný způsob' }
  ];

  function dateOnly(value) {
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function periodBounds(period, now) {
    const today = dateOnly(now) || new Date();
    if (period === 'all') return { from: null, to: null };
    if (period === 'custom') return { from: null, to: null };
    if (period === 'season') {
      const year = today.getMonth() >= 8 ? today.getFullYear() : today.getFullYear() - 1;
      return { from: new Date(Date.UTC(year, 8, 1)), to: new Date(Date.UTC(year + 1, 7, 31, 23, 59, 59)) };
    }
    return { from: new Date(today.getTime() - 365 * 24 * 60 * 60 * 1000), to: today };
  }

  function inPeriod(value, options) {
    const date = dateOnly(value);
    if (!date) return options.period === 'all';
    let bounds = periodBounds(options.period || 'last12', options.now);
    if (options.period === 'custom') bounds = { from: dateOnly(options.dateFrom), to: dateOnly(options.dateTo) };
    if (bounds.from && date < bounds.from) return false;
    if (bounds.to && date > bounds.to) return false;
    return true;
  }

  function selectBestPerformance(performances, stroke, options) {
    const candidates = (performances || []).filter((entry) => entry.stroke === stroke && Number(entry.distance) === Number(options.distance) && Number(entry.poolLength) === Number(options.poolLength) && (options.includeRelaySplits || !entry.relayPart) && inPeriod(entry.date, options) && Number.isFinite(Number(entry.timeMs)) && Number(entry.timeMs) > 0);
    return candidates.sort((a, b) => Number(a.timeMs) - Number(b.timeMs) || String(b.date).localeCompare(String(a.date)))[0] || null;
  }

  function buildMatrix(swimmers, options) {
    return (swimmers || []).map((swimmer) => {
      const times = {};
      STROKES.forEach((stroke) => {
        const manual = options.manualTimes && options.manualTimes[swimmer.id] && options.manualTimes[swimmer.id][stroke.key];
        const manualMs = Number(manual);
        times[stroke.key] = Number.isFinite(manualMs) && manualMs > 0 ? { timeMs: manualMs, source: 'manual', swimmer } : selectBestPerformance(swimmer.performances, stroke.key, options);
      });
      return { swimmer, times };
    });
  }

  function optimize(swimmers, options) {
    const matrix = buildMatrix(swimmers, options || {});
    const results = [];
    function visit(strokeIndex, used, legs, total) {
      if (strokeIndex === STROKES.length) {
        results.push({ legs: legs.slice(), totalMs: total, signature: legs.map((leg) => leg.swimmer.id).join('-') });
        return;
      }
      const stroke = STROKES[strokeIndex];
      matrix.forEach((row) => {
        if (used.has(row.swimmer.id) || !row.times[stroke.key]) return;
        const time = row.times[stroke.key];
        visit(strokeIndex + 1, new Set([...used, row.swimmer.id]), [...legs, { stroke, swimmer: row.swimmer, performance: time }], total + Number(time.timeMs));
      });
    }
    visit(0, new Set(), [], 0);
    results.sort((a, b) => a.totalMs - b.totalMs || a.signature.localeCompare(b.signature));
    return { matrix, results: results.slice(0, 3) };
  }

  return { STROKES, inPeriod, selectBestPerformance, buildMatrix, optimize };
}));
