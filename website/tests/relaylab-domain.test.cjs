const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const worker = require('../main-site-worker.ts').default;
const origin = 'https://relaylab.tomaspisar.cz';

test('RelayLab legacy URLs redirect directly and preserve queries and suffixes', async () => {
  for (const host of ['https://tomaspisar.cz', 'https://www.tomaspisar.cz', origin]) {
    for (const prefix of ['/products/relaylab', '/software/relaylab', '/swimming/relaylab']) {
      for (const [suffix, target] of [['', '/'], ['/', '/'], ['/index.html', '/'], ['/example', '/example']]) {
        const response = await worker.fetch(new Request(`${host}${prefix}${suffix}?pool=25`), {});
        assert.equal(response.status, 301);
        assert.equal(response.headers.get('location'), `${origin}${target}?pool=25`);
      }
    }
  }
});

test('RelayLab root serves the app internally and assets stay on the same origin', async () => {
  for (const [url, expected] of [['/?pool=25', '/products/relaylab/'], ['/assets/css/pages/relaylab.css?v=1', '/assets/css/pages/relaylab.css?v=1']]) {
    let fetched;
    const response = await worker.fetch(new Request(origin + url), { ASSETS: { fetch: async request => { fetched = new URL(request.url); return new Response('asset'); } } });
    assert.equal(response.status, 200);
    assert.equal(fetched.pathname + fetched.search, expected);
    assert.equal(fetched.origin, origin);
  }
  const api = await worker.fetch(new Request(`${origin}/api/swimming/search?q=x`), {});
  assert.equal(api.status, 400);
  assert.equal((await api.json()).error.code, 'query_too_short');
});

test('RelayLab site metadata is isolated and public links lead back to the main site', async () => {
  for (const pathname of ['/robots.txt', '/sitemap.xml']) {
    const response = await worker.fetch(new Request(origin + pathname), {});
    assert.equal(response.status, 200);
    assert.match(await response.text(), /https:\/\/relaylab\.tomaspisar\.cz\//);
  }
  const response = await worker.fetch(new Request(`${origin}/products/?lang=cs`), {});
  assert.equal(response.headers.get('location'), 'https://tomaspisar.cz/products/?lang=cs');
  const config = JSON.parse(fs.readFileSync(path.join(__dirname, '../wrangler.jsonc'), 'utf8'));
  assert.equal(config.assets.run_worker_first, true);
  assert.ok(config.routes.some(route => route.pattern === 'relaylab.tomaspisar.cz' && route.custom_domain));
  const page = fs.readFileSync(path.join(__dirname, '../tomaspisar.cz/products/relaylab/index.html'), 'utf8');
  assert.match(page, /rel="canonical" href="https:\/\/relaylab\.tomaspisar\.cz\/"/);
  assert.match(page, /href="https:\/\/tomaspisar\.cz\/products\/"/);
});

test('migration destinations cannot change origin through double slashes', async () => {
  for (const [source, expected] of [
    ['https://tomaspisar.cz/products/relaylab//example.org/', 'https://relaylab.tomaspisar.cz//example.org/'],
    ['https://relaylab.tomaspisar.cz//example.org/', 'https://tomaspisar.cz//example.org/']
  ]) {
    const response = await worker.fetch(new Request(source), {});
    assert.equal(response.headers.get('location'), expected);
  }
});
