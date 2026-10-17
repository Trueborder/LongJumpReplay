const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const source=fs.readFileSync('tomaspisar.cz/account/economysuite/app.js','utf8');
test('rank presentation distinguishes seven-day products from currency and includes shared benefits',()=>{
  assert.match(source,/function productLabel/);assert.match(source,/function rankPanel/);assert.match(source,/function rankComparison/);
  assert.match(source,/remaining_ms/);assert.match(source,/604|168/);assert.match(source,/Without|without stacking/);
  assert.doesNotMatch(source,/\['title', t\('Titul'/);assert.match(source,/\['prefix', 'color', 'aura', 'hat'\]\.map/);
});
test('rank copy discloses payment-time expiry and paused lower-tier time in both languages',()=>{
  assert.match(source,/Sedm dní běží od potvrzení platby i offline/);
  assert.match(source,/Seven days run from payment confirmation including offline time/);
  assert.match(source,/a higher rank pauses lower-tier time/);
});
