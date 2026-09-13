const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const publicRoot = path.join(root, 'tomaspisar.cz');
const worker = fs.readFileSync(path.join(root, 'main-site-worker.ts'), 'utf8');
const siteScript = fs.readFileSync(path.join(publicRoot, 'assets', 'js', 'components', 'site.js'), 'utf8');
const componentCss = fs.readFileSync(path.join(publicRoot, 'assets', 'css', 'components.css'), 'utf8');
const htmlFiles = [];
const collectHtml = (directory) => {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) collectHtml(target);
    else if (entry.name.endsWith('.html')) htmlFiles.push(target);
  }
};
collectHtml(publicRoot);

test('product and legal pages use the organized public structure', () => {
  assert.ok(fs.existsSync(path.join(publicRoot, 'products', 'long-jump-replay', 'index.html')));
  assert.ok(fs.existsSync(path.join(publicRoot, 'products', 'relaylab', 'index.html')));
  assert.ok(fs.existsSync(path.join(publicRoot, 'legal', 'privacy', 'index.html')));
  assert.equal(fs.existsSync(path.join(publicRoot, 'software')), false);
  assert.equal(fs.existsSync(path.join(publicRoot, 'privacy')), false);
});

test('legacy product routes redirect permanently and keep nested suffixes', () => {
  assert.match(worker, /function legacyRouteRedirect/);
  assert.match(worker, /\/products\/long-jump-replay/);
  assert.match(worker, /\/products\/relaylab/);
  assert.match(worker, /status: 301/);
  assert.match(worker, /\/legal\/privacy\//);
});

test('global downloads navigation is removed without removing download actions', () => {
  for (const file of htmlFiles) {
    const html = fs.readFileSync(file, 'utf8');
    assert.doesNotMatch(html, /data-ui="downloads"/);
  }
  assert.match(fs.readFileSync(path.join(publicRoot, 'products', 'long-jump-replay', 'download', 'index.html'), 'utf8'), /data-installer-url/);
  assert.match(siteScript, /Download/);
});

test('LongJumpReplay uses a compact contextual product navigation row', () => {
  assert.match(siteScript, /product-context-nav/);
  assert.match(siteScript, /data-product-context/);
  assert.match(siteScript, /Licensing/);
  assert.match(siteScript, /Privacy/);
  assert.doesNotMatch(siteScript, /en: 'Download', cs: 'Stáhnout'/);
  assert.match(componentCss, /\.product-context-nav/);
  assert.match(componentCss, /\.product-context-links/);
});
