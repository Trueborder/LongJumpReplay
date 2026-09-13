const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const siteRoot = path.join(__dirname, '..', 'tomaspisar.cz');
const html = fs.readFileSync(path.join(siteRoot, 'welcome', 'index.html'), 'utf8');
const downloadPage = fs.readFileSync(path.join(siteRoot, 'products', 'long-jump-replay', 'download', 'index.html'), 'utf8');
const css = fs.readFileSync(path.join(siteRoot, 'assets', 'css', 'components.css'), 'utf8');
const script = fs.readFileSync(path.join(siteRoot, 'assets', 'js', 'components', 'site.js'), 'utf8');

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

test('download warning opens after the installer download starts', () => {
  assert.match(html, /<dialog class="download-safety-dialog" data-download-safety-dialog/);
  assert.match(html, /DOWNLOAD STARTED/);
  assert.match(html, /data-download-safety-close/);
  assert.match(script, /window\.setTimeout\(\(\) => \{/);
  assert.match(script, /downloadSafetyDialog\.showModal\(\)/);
  assert.match(script, /downloadSafetyTrigger\?\.focus\(\)/);
  assert.match(css, /\.download-safety-dialog::backdrop/);
});

test('the canonical download page creates the warning dialog when its installer link is clicked', () => {
  assert.match(downloadPage, /data-installer-url/);
  assert.match(script, /if \(installerLinks\.length && !downloadSafetyDialog\)/);
  assert.match(script, /template\.innerHTML = `[\s\S]*data-download-safety-dialog/);
  assert.match(script, /document\.body\.append\(downloadSafetyDialog\)/);
  assert.match(script, /installerLinks\.forEach\(\(element\) => \{/);
});

test('customer downloads keep the cache-safe stable installer alias', () => {
  assert.match(downloadPage, /data-installer-url href="https:\/\/files\.tomaspisar\.cz\/LJR_setup\.exe"/);
  assert.match(script, /element\.href = product\.installerUrl/);
  assert.doesNotMatch(script, /element\.href = installer\.href/);
});

test('purchase confirmation uses plural company voice', () => {
  assert.doesNotMatch(html, /(?:I will|writing to me|write to me|Email me)/i);
  assert.doesNotMatch(html, /(?:napište mi\b|vyřeším(?:\s|[.,]))/i);
  assert.match(html, /we will sort it out/);
  assert.match(html, /Email us/);
  assert.match(html, /vyřešíme to/);
});
