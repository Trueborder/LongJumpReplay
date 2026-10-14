const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = path.join(__dirname,'../tomaspisar.cz/account/economysuite');
const css = fs.readFileSync(path.join(base,'app.css'),'utf8').split('/* Extend the portal')[1];
test('portal loads scoped motion in its existing stylesheet and disables repeated data entrances',()=>{
  const html=fs.readFileSync(path.join(base,'index.html'),'utf8');
  assert.ok(html.includes('/economysuite/app.css?v=20261014-motion'));
  assert.match(css,/#content[^\n]+animation:none/);
  assert.match(css,/\.es-command:focus-visible\{transform:none\}/);
});
test('portal drawer motion is reversible, compositor-only and keyboard/reduced-motion safe',()=>{
  assert.match(css,/display 220ms allow-discrete,overlay 220ms allow-discrete/);
  assert.match(css,/@starting-style/);
  assert.match(css,/data-motion-input=keyboard/);
  assert.match(css,/prefers-reduced-motion:reduce/);
  assert.doesNotMatch(css,/transition:\s*all|transition:[^;}]*\b(?:height|width|top|left|padding|margin)\s+\d/);
  const script=fs.readFileSync(path.join(base,'app.js'),'utf8');
  assert.match(script,/addEventListener\('keydown',[^\n]+motionInput = 'keyboard'/);
  assert.match(script,/addEventListener\('pointerdown',[^\n]+motionInput = 'pointer'/);
});
