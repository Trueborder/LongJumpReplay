const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..', 'tomaspisar.cz');
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8');
const sharedScript = read('assets/js/components/site.js');
const accountScript = read('assets/js/account/account.js');
const contactScript = read('assets/js/pages/contact.js');
const relayScript = read('assets/js/pages/relaylab.js');
const componentsCss = read('assets/css/components.css');

test('shared feedback primitives cover toast, inline, and modal decisions', () => {
  assert.match(sharedScript, /window.LJR_FEEDBACK = feedback/);
  assert.match(sharedScript, /toast: { success:/);
  assert.match(sharedScript, /const setInline =/);
  assert.match(sharedScript, /const confirm =/);
  assert.match(sharedScript, /beforetoggle/);
  assert.match(componentsCss, /.toast-region/);
  assert.match(componentsCss, /.feedback-modal/);
  assert.match(componentsCss, /.inline-message/);
});

test('destructive account actions use the reusable modal and successes use toasts', () => {
  assert.doesNotMatch(accountScript, /window\.confirm\s*\(/);
  assert.match(accountScript, /feedback\?\.confirm/);
  assert.match(accountScript, /notify\('success'/);
  assert.match(accountScript, /readableError/);
});

test('form and RelayLab feedback stays contextual', () => {
  assert.match(contactScript, /feedback\?\.inline/);
  assert.match(contactScript, /toast.success/);
  assert.match(relayScript, /setSearchFeedback/);
  assert.match(relayScript, /toast.success/);
});

test('website scripts contain no browser alert or confirm calls', () => {
  const scripts = [
    ...fs.globSync(path.join(root, '**', '*.js'), { exclude: (file) => file.includes('node_modules') })
  ].map((file) => fs.readFileSync(file, 'utf8')).join('\n');
  assert.doesNotMatch(scripts, /\b(?:window\.)?(?:alert|confirm)\s*\(/);
});
