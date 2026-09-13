const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const siteRoot = path.join(__dirname, '..', 'tomaspisar.cz');
const script = fs.readFileSync(path.join(siteRoot, 'assets', 'js', 'components', 'site.js'), 'utf8');
const css = [
  path.join('assets', 'css', 'tokens.css'),
  path.join('assets', 'css', 'global.css'),
  path.join('assets', 'css', 'pages', 'legacy.css'),
  path.join('assets', 'css', 'components.css'),
  path.join('assets', 'css', 'pages', 'account.css')
].map((file) => fs.readFileSync(path.join(siteRoot, file), 'utf8')).join('\n');

const htmlFiles = [];
const collectHtml = (directory) => {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) collectHtml(target);
    else if (entry.name.endsWith('.html')) htmlFiles.push(target);
  }
};
collectHtml(siteRoot);

test('every page is explicitly light and exposes no theme control or resolver', () => {
  assert.ok(htmlFiles.length >= 12);
  for (const file of htmlFiles) {
    const html = fs.readFileSync(file, 'utf8');
    assert.match(html, /<html\b[^>]*data-theme="light"/, path.relative(siteRoot, file));
    assert.doesNotMatch(html, /data-theme-toggle|site-theme|prefers-color-scheme/, path.relative(siteRoot, file));
  }
});

test('runtime has no dark or system appearance mode', () => {
  assert.doesNotMatch(script, /data-theme-toggle|themePreference|prefers-color-scheme|themeSystem|themeLight|themeDark|setTheme/);
  assert.doesNotMatch(css, /html\[data-theme|color-scheme:\s*dark|--bg:\s*#(?:0b1013|081018)/i);
  assert.match(css, /color-scheme:\s*light/);
  assert.match(css, /--bg:\s*#f2f0e9/i);
});

test('obsolete stored theme preferences are removed', () => {
  assert.match(script, /deleteCookie\('site-theme'\)/);
  assert.match(script, /sessionStorage\.removeItem\('site-theme'\)/);
});

test('accepted preferences are shared with the account subdomain', () => {
  assert.match(script, /Domain=tomaspisar\.cz/);
  assert.match(script, /Remove an older host-only value/);
});
