const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const siteRoot = path.join(__dirname, '..', 'tomaspisar.cz');
const script = fs.readFileSync(path.join(siteRoot, 'script.js'), 'utf8');
const css = fs.readFileSync(path.join(siteRoot, 'overrides.css'), 'utf8');

const htmlFiles = [];
const collectHtml = (directory) => {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) collectHtml(target);
    else if (entry.name.endsWith('.html')) htmlFiles.push(target);
  }
};
collectHtml(siteRoot);

test('every page with a theme control restores cookie or session preference before body paint', () => {
  const pages = htmlFiles.filter((file) => fs.readFileSync(file, 'utf8').includes('data-theme-toggle'));
  assert.ok(pages.length >= 10);
  for (const file of pages) {
    const html = fs.readFileSync(file, 'utf8');
    assert.match(html, /sessionStorage\.getItem\('site-theme'\)/, path.relative(siteRoot, file));
    assert.match(html, /dataset\.themePreference=p/, path.relative(siteRoot, file));
    assert.doesNotMatch(html, /a&&m&&decodeURIComponent\(m\[1\]\)==='light'\?'light':'dark'/, path.relative(siteRoot, file));
  }
});

test('theme control exposes localized System, Light, and Dark labels', () => {
  assert.match(script, /themeSystem: 'System', themeLight: 'Light', themeDark: 'Dark'/);
  assert.match(script, /themeSystem: 'Systém', themeLight: 'Světlý', themeDark: 'Tmavý'/);
  assert.match(script, /class="theme-label"/);
  assert.match(css, /\.icon-button\[data-theme-toggle\][^{]*\{[^}]*width: auto;/);
});

test('theme choices survive page navigation without optional preference cookies', () => {
  assert.match(script, /sessionStorage\.setItem\(name, value\)/);
  assert.match(script, /return readSessionPref\(name\)/);
  assert.match(script, /current === 'system' \? 'light' : current === 'light' \? 'dark' : 'system'/);
});

test('accepted preferences are shared with the account subdomain', () => {
  assert.match(script, /Domain=tomaspisar\.cz/);
  assert.match(script, /Remove an older host-only value/);
});
