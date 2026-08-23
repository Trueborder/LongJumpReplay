const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const siteRoot = path.join(__dirname, '..', 'tomaspisar.cz');
const html = fs.readFileSync(path.join(siteRoot, 'welcome', 'index.html'), 'utf8');
const css = fs.readFileSync(path.join(siteRoot, 'overrides.css'), 'utf8');

test('purchase confirmation shows download and SmartScreen guidance beside the installer action', () => {
  const download = html.indexOf('data-installer-url');
  const alert = html.indexOf('class="download-safety-alert"');
  assert.ok(download >= 0);
  assert.ok(alert > download);
  assert.ok(alert - download < 1500, 'safety alert should remain directly beside the download action');
  assert.match(html, /files\.tomaspisar\.cz/);
  assert.match(html, /LJR_setup\.exe/);
  assert.match(html, /More info/);
  assert.match(html, /Přesto spustit/);
  assert.match(css, /\.download-safety-alert \{[^}]*border-left: 5px solid var\(--amber\)/);
  assert.match(css, /\.download-safety-steps \{[^}]*grid-template-columns: repeat\(2/);
});
