const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..', 'tomaspisar.cz');
const publicPages = [
  'index.html',
  'about/index.html',
  'contact/index.html',
  'products/index.html',
  'products/economysuite/index.html',
  'products/long-jump-replay/index.html',
  'account/login/index.html',
  'account/economysuite/index.html',
];

test('Novaryn Solutions logo assets and brand entry points are published', () => {
  const branding = path.join(root, 'assets', 'images', 'branding');
  for (const file of [
    'novaryn-solutions-wordmark-light.png',
    'novaryn-solutions-wordmark-dark.png',
    'novaryn-solutions-symbol.png',
    'novaryn-solutions-badge.png',
  ]) {
    const bytes = fs.readFileSync(path.join(branding, file));
    assert.deepEqual([...bytes.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10], file);
  }

  for (const relative of publicPages) {
    const html = fs.readFileSync(path.join(root, relative), 'utf8');
    assert.match(html, /Novaryn Solutions/);
    assert.match(html, /novaryn-solutions-symbol\.png/);
  }
  assert.ok(fs.existsSync(path.join(root, 'design-system', 'novaryn-solutions', 'MASTER.md')));
});

test('public assets use the new brand without exposing the retired personal identity', () => {
  const files = [];
  const visit = directory => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const file = path.join(directory, entry.name);
      if (entry.isDirectory()) visit(file);
      else if (/\.(html|js|css|md)$/.test(entry.name)) files.push(file);
    }
  };
  visit(root);
  for (const file of files) {
    const content = fs.readFileSync(file, 'utf8');
    assert.doesNotMatch(content, /Tomáš Pisár|Tomas Pisar|Tomáši Pisárovi|TP \/ ABOUT/);
    assert.doesNotMatch(content, /\/assets\/(?:icons\/)?favicon\.svg/);
  }

  const siteScript = fs.readFileSync(path.join(root, 'assets', 'js', 'components', 'site.js'), 'utf8');
  assert.match(siteScript, /novaryn-solutions-symbol\.png/);
});
