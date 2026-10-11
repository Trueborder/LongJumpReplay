const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..', 'tomaspisar.cz');
const legalRoot = path.join(root, 'legal');
const pages = fs.readdirSync(legalRoot).map(name => name === 'index.html' ? path.join(legalRoot, name) : path.join(legalRoot, name, 'index.html'));

test('every legal page loads the same layout foundation as the public homepage, before document styles', () => {
  for (const file of pages) {
    const html = fs.readFileSync(file, 'utf8');
    const styles = [...html.matchAll(/<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"/g)].map(match => match[1].split('?')[0]);
    for (const asset of styles.filter(href => href.startsWith('/'))) assert.ok(fs.existsSync(path.join(root, asset)), `${file}: missing ${asset}`);
    assert.ok(styles.indexOf('/assets/css/pages/legacy.css') >= 0, `${file}: missing public-site reset and centering`);
    assert.ok(styles.indexOf('/assets/css/pages/legacy.css') < styles.indexOf('/assets/css/components.css'));
    assert.ok(styles.indexOf('/assets/css/components.css') < styles.indexOf('/assets/css/pages/legal.css'));
    assert.match(html, /data-menu-toggle/, `${file}: mobile navigation must be reachable`);
    assert.match(html, /class="site-header"/);
    assert.match(html, /class="site-footer"/);
    assert.match(html, /assets\/js\/components\/site\.js/);
  }
});

test('legal directory exposes every published document, with no broken local links', () => {
  const html = fs.readFileSync(path.join(legalRoot, 'index.html'), 'utf8');
  const links = [...html.matchAll(/href="(\/legal\/[^"#]+)"/g)].map(match => match[1]);
  for (const file of pages.filter(file => file !== path.join(legalRoot, 'index.html'))) {
    const href = '/' + path.relative(root, path.dirname(file)).split(path.sep).join('/') + '/';
    assert.ok(links.includes(href), `${href} missing from directory`);
  }
  for (const link of links) assert.ok(fs.existsSync(path.join(root, link, 'index.html')), `${link} has no document`);
});

test('document contents anchors resolve to unique headings and have an accessible summary', () => {
  for (const file of pages.filter(file => path.dirname(file) !== legalRoot)) {
    const html = fs.readFileSync(file, 'utf8');
    assert.match(html, /class="legal-back"/);
    const ids = [...html.matchAll(/id="([^"]+)"/g)].map(match => match[1]);
    assert.equal(new Set(ids).size, ids.length, `${file}: duplicate ids`);
    const headings = [...html.matchAll(/<h2[^>]*id="(legal-section-\d+)"/g)].map(match => match[1]);
    if (headings.length >= 4) {
      assert.match(html, /<summary[^>]+data-cs="Obsah dokumentu"[^>]+data-en="Document contents"/);
      for (const id of headings) assert.match(html, new RegExp(`href="#${id}"`));
    }
  }
});
