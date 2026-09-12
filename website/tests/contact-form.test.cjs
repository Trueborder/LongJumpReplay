const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const siteRoot = path.resolve(__dirname, '..', 'tomaspisar.cz');
const html = fs.readFileSync(path.join(siteRoot, 'contact', 'index.html'), 'utf8');
const script = fs.readFileSync(path.join(siteRoot, 'contact-form.js'), 'utf8');
const config = fs.readFileSync(path.join(siteRoot, 'site.config.js'), 'utf8');

test('contact page uses a labelled form and keeps direct support contact visible', () => {
  assert.match(html, /<form data-contact-form novalidate>/);
  for (const field of ['name', 'email', 'topic', 'message']) {
    assert.match(html, new RegExp(`name="${field}"`));
  }
  assert.match(html, /name="website"/);
  assert.match(html, /data-contact-turnstile/);
  assert.match(html, /class="contact-page-email"[^>]+href="mailto:info@tomaspisar\.cz"/);
  assert.match(html, /<option value="club" data-en="Club licence \/ better price" data-cs="Klubová licence \/ lepší cena">/);
});

test('contact client posts to configured API and requests invisible Turnstile', () => {
  assert.match(config, /api\.tomaspisar\.cz\/api\/contact/);
  assert.match(script, /size: 'invisible'/);
  assert.match(script, /turnstile_token/);
  assert.match(script, /fetch\(config\.apiUrl/);
});
