const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const css = fs.readFileSync(
  path.resolve(__dirname, '..', 'tomaspisar.cz', 'assets', 'css', 'components.css'),
  'utf8',
);

test('the shared website header stays fixed while the page scrolls', () => {
  assert.match(css, /--site-header-reserved-space:\s*76px/);
  assert.match(css, /body\s*\{[^}]*padding-top:\s*var\(--site-header-reserved-space\)/s);
  assert.match(css, /\.site-header\s*\{[^}]*position:\s*fixed/s);
  assert.match(css, /\.site-header\s*\{[^}]*top:\s*\.75rem/s);
  assert.match(css, /\.site-header\s*\{[^}]*right:\s*0[^}]*left:\s*0/s);
  assert.match(css, /@media\s*\(max-width:\s*650px\)\s*\{[^}]*--site-header-reserved-space:\s*72px/s);
});
