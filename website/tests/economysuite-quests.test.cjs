const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('tomaspisar.cz/account/economysuite/app.js', 'utf8');
function render(snapshot, lang = 'cs') {
  const code = source.slice(source.indexOf('  function currentTasks('), source.indexOf('  function jobTask('));
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const context = { snapshot, t: (cs,en) => lang === 'cs' ? cs : en, escape, strip: v => String(v).replace(/&[0-9a-fklmnor]/gi,''), number: v => String(Number(v || 0)), row: cells => '<tr>' + cells.map(c => '<td>' + c + '</td>').join('') + '</tr>', table: (heads,rows) => heads.join('|') + rows.join('') };
  vm.createContext(context); return vm.runInContext(code + ';currentTasks(snapshot)',context);
}
test('overview and progress render only authoritative daily/weekly tasks with reward and cycle', () => {
  const html = render({ progress: { tasks_version: 2, daily: [{id:'mine',name:'&eKámen',progress:42,target:100,reward_coins:50,points:1}], weekly: [{id:'hunt',name:'Lov',progress:10,target:10,complete:true,reward_coins:200,points:5}], cycles: { daily:'2026-10-20',weekly:'2026-10-19' } } });
  for (const text of ['Denní úkoly','Týdenní úkoly','Kámen','42 / 100','50 coins','200 coins','Dokončeno','2026-10-20']) assert.ok(html.includes(text),text);
  assert.match(source,/panel\(t\('Denní a týdenní úkoly', 'Daily and weekly tasks'\), currentTasks\(snapshot\)/);
});
test('old batches never reappear and empty/malicious snapshots are safe in both languages', () => {
  assert.doesNotMatch(render({progress:{tasks:[{name:'OLD BATCH'}]}}),/OLD BATCH/);
  assert.match(render({},'en'),/Weekly tasks/);assert.match(render({},'en'),/Waiting for daily and weekly/);
  const html=render({progress:{tasks_version:2,daily:[{name:'<script>alert(1)</script>',target:1}],cycles:{daily:'<img>'}}});assert.doesNotMatch(html,/<script>|<img>/);assert.match(html,/&lt;script&gt;/);
  assert.doesNotMatch(source,/snapshot\.progress\??\.tasks\b/);
});
