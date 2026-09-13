const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const siteRoot = path.resolve(__dirname, '..', 'tomaspisar.cz');
const page = fs.readFileSync(path.join(siteRoot, '404.html'), 'utf8');
const config = fs.readFileSync(path.resolve(__dirname, '..', 'wrangler.jsonc'), 'utf8');

test('the website has a bilingual styled 404 fallback', () => {
  assert.match(page, /<meta name="robots" content="noindex">/);
  assert.match(page, /class="[^"]*not-found-page[^"]*"/);
  assert.match(page, /data-en="This page is not here\."/);
  assert.match(page, /data-cs="Tato stránka tu není\."/);
  assert.match(page, /href="\/"/);
  assert.match(page, /href="\/software\/"/);
});

test('Workers Assets is configured to serve the 404 page for unknown paths', () => {
  assert.match(config, /"not_found_handling"\s*:\s*"404-page"/);
});
